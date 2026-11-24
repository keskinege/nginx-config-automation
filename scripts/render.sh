#!/usr/bin/env bash
# Render one group's config tree from NIM config templates + variables.
#
#   GROUP=static-cluster \
#   NIM_URL=https://<nim-host> NIM_USER=… NIM_PASSWORD=… \
#   ./scripts/render.sh
#
# Reads:  groups/$GROUP/inputs.yaml (falls back to inputs.json)
# Writes: ${OUT_DIR:-rendered/$GROUP}/nginx.conf, conf.d/*.conf, …
#         plus render-manifest.txt
#
# Templates must already exist in NIM. A template is resolved by:
#   1. templateUID already present in the inputs
#   2. .nim/templates.lock.json: name -> uid (or { "uid": ... })
#   3. GET /conf-templates, matched by name
#
# Env:
#   MODE=compose      (default) PUT /conf-templates/config
#   MODE=submissions  PUT /conf-templates/submissions/config; needs a target,
#                     taken from inputs.instanceGroupUID or resolved from GROUP.
#                     Use this for augment-only composition (no baseData).
#   DRY_RUN=1         compose, print the file list + hash, write nothing.
#   HASH_ONLY=1       compose, print sha256/crc32/files/bytes, write nothing.
#   CHECK_HASH=1      compare the rendered tree hash to HASH_FILE; exit 2 on change.
#   WRITE_HASH=1      record the rendered tree hash in HASH_FILE.
#   EXPECTED_SHA256   fail (exit 2) unless the rendered tree hash matches.
#   HASH_FILE         hash lock path (default .nim/rendered.lock.json).
#   WRITE_LOCK=1      merge resolved name -> uid pairs into .nim/templates.lock.json.
#   ROOT_DIR          managed root used to shorten absolute paths (default /etc/nginx).
#   NIM_MGMT_ENDPOINT replaces the mgmt "nim-mgmt-endpoint.invalid" placeholder in the
#                     rendered tree. Required whenever the tree still contains it.
#   MGMT_PLACEHOLDER  placeholder text to replace (default nim-mgmt-endpoint.invalid).
#   INPUTS            explicit inputs file (default groups/$GROUP/inputs.{yaml,json}).
#   OUT_DIR           output directory (default rendered/$GROUP).
#
# YAML inputs need `yq` (mikefarah v4). JSON inputs need only python3.
set -euo pipefail

: "${GROUP:?set GROUP (the group directory name)}"
: "${NIM_URL:?set NIM_URL}"
: "${NIM_USER:?set NIM_USER}"
: "${NIM_PASSWORD:?set NIM_PASSWORD}"

cd "$(dirname "$0")/.."

if [ ! -d "groups/$GROUP" ]; then
  echo "::error::no such group directory: groups/$GROUP"
  exit 1
fi

INPUTS="${INPUTS:-groups/$GROUP/inputs.yaml}"
if [ ! -f "$INPUTS" ] && [ -f "groups/$GROUP/inputs.json" ]; then
  INPUTS="groups/$GROUP/inputs.json"
fi
if [ ! -f "$INPUTS" ]; then
  echo "::error::missing inputs for $GROUP: expected groups/$GROUP/inputs.yaml or .json"
  exit 1
fi

OUT_DIR="${OUT_DIR:-rendered/$GROUP}"
LOCK_FILE="${LOCK_FILE:-.nim/templates.lock.json}"
ROOT_DIR="${ROOT_DIR:-/etc/nginx}"
MODE="${MODE:-compose}"
DRY_RUN="${DRY_RUN:-0}"
HASH_ONLY="${HASH_ONLY:-0}"
CHECK_HASH="${CHECK_HASH:-0}"
WRITE_HASH="${WRITE_HASH:-0}"
HASH_FILE="${HASH_FILE:-.nim/rendered.lock.json}"
EXPECTED_SHA256="${EXPECTED_SHA256:-}"
WRITE_LOCK="${WRITE_LOCK:-0}"
NIM_MGMT_ENDPOINT="${NIM_MGMT_ENDPOINT:-}"
MGMT_PLACEHOLDER="${MGMT_PLACEHOLDER:-nim-mgmt-endpoint.invalid}"
TEMPLATE_PREFIX="${TEMPLATE_PREFIX:-}"
BASE="${NIM_URL%/}/api/platform/v1"
NIM_CA="${NIM_CA:-certs/nim-ca.pem}"
CURL=(curl -sS -m 30 --cacert "$NIM_CA" -u "$NIM_USER:$NIM_PASSWORD")
if [ -n "${NIM_HOST:-}" ]; then
  CURL+=(--resolve "manager-server:443:$NIM_HOST")
fi

# OUT_DIR is deleted before it is written. Only replace a render output: a
# path under rendered/, a path that does not exist yet, or a directory that
# carries a render-manifest.txt from an earlier render.
case "$OUT_DIR" in
  ""|"/"|"."|"..") echo "::error::refusing OUT_DIR=$OUT_DIR"; exit 1 ;;
  groups|groups/|groups/*|templates|templates/|templates/*|\
  scripts|scripts/|scripts/*|certs|certs/|certs/*|.git|.git/*)
    echo "::error::refusing to write over repository content: $OUT_DIR"
    exit 1 ;;
  rendered|rendered/*) ;;
  *)
    if [ -e "$OUT_DIR" ] && [ ! -f "$OUT_DIR/render-manifest.txt" ]; then
      echo "::error::refusing to replace '$OUT_DIR': no render-manifest.txt from an earlier render"
      exit 1
    fi ;;
esac

api() {
  local attempt rc
  for attempt in 1 2 3; do
    if "${CURL[@]}" "$@"; then return 0; fi
    rc=$?
    if [ "$attempt" -eq 3 ]; then return "$rc"; fi
    echo "api: attempt $attempt failed (curl $rc); retrying in $((attempt * 5))s" >&2
    sleep $((attempt * 5))
  done
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# 1. inputs -> JSON
case "$INPUTS" in
  *.json) cp "$INPUTS" "$tmp/inputs.json" ;;
  *)
    if ! command -v yq >/dev/null 2>&1; then
      echo "::error::yq is required for YAML inputs (or use inputs.json)"
      exit 1
    fi
    yq -o=json '.' "$INPUTS" > "$tmp/inputs.json"
    ;;
esac

# 2. list templates (paginated) for name -> uid resolution
offset=0
: > "$tmp/pages.jsonl"
while :; do
  api "$BASE/conf-templates?limit=100&offset=$offset" > "$tmp/page.json"
  n=$(jq -r '(.items // []) | length' "$tmp/page.json")
  jq -c '.items // []' "$tmp/page.json" >> "$tmp/pages.jsonl"
  [ "$n" -lt 100 ] && break
  offset=$((offset + 100))
done
jq -s '{items: add}' "$tmp/pages.jsonl" > "$tmp/templates.json"

# 3. resolve template UIDs and build the compose body
python3 - "$tmp/inputs.json" "$LOCK_FILE" "$tmp/templates.json" "$tmp/body.json" "$tmp/resolved.json" \
  "$TEMPLATE_PREFIX" <<'PY'
import json, pathlib, sys

inputs_path, lock_path, templates_path, body_path, resolved_path = sys.argv[1:6]
prefix = sys.argv[6] if len(sys.argv) > 6 else ""
body = json.loads(pathlib.Path(inputs_path).read_text())

lock = {}
lock_file = pathlib.Path(lock_path)
if lock_file.exists():
    try:
        lock = json.loads(lock_file.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid lock file {lock_file}: {exc}")

templates = json.loads(pathlib.Path(templates_path).read_text()).get("items", [])
by_name = {t.get("name"): t.get("uid") for t in templates if t.get("name")}

def lock_uid(name):
    value = lock.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("uid")
    return None

def resolve(obj, label):
    uid = obj.get("templateUID")
    name = obj.get("templateName")
    if uid:
        return str(uid), name
    if not name:
        raise SystemExit(f"{label}: needs templateUID or templateName")
    lookup = f"{prefix}{name}"
    # A throwaway (pr-<n>-) namespace has its own UIDs, so the lock must not win.
    uid = (None if prefix else lock_uid(name)) or by_name.get(lookup)
    if not uid:
        raise SystemExit(
            f"{label}: template '{lookup}' not found in NIM"
            + ("" if prefix else f" or {lock_path}")
        )
    obj["templateUID"] = uid
    return str(uid), name

resolved = {}
base = body.get("baseData")
if base:
    uid, name = resolve(base, "baseData")
    resolved[name or uid] = uid
for i, aug in enumerate(body.get("augmentData") or []):
    uid, name = resolve(aug, f"augmentData[{i}]")
    resolved[name or uid] = uid

pathlib.Path(body_path).write_text(json.dumps(body, sort_keys=True))
pathlib.Path(resolved_path).write_text(json.dumps(resolved, sort_keys=True))
PY

# 4. compose
if [ "$MODE" = "submissions" ]; then
  if ! jq -e '.instanceGroupUID' "$tmp/body.json" >/dev/null 2>&1; then
    GROUP_UID=$(api "$BASE/instance-groups" \
      | jq -r --arg n "$GROUP" '.items[]? | select(.name==$n) | .uid' | head -1)
    if [ -z "$GROUP_UID" ] || [ "$GROUP_UID" = "null" ]; then
      echo "::error::instance group '$GROUP' not found at $NIM_URL"
      exit 1
    fi
    jq --arg uid "$GROUP_UID" '. + {instanceGroupUID: $uid}' "$tmp/body.json" > "$tmp/body.target.json"
    mv "$tmp/body.target.json" "$tmp/body.json"
  fi
  ENDPOINT="$BASE/conf-templates/submissions/config"
else
  if ! jq -e '.baseData' "$tmp/body.json" >/dev/null 2>&1; then
    echo "::error::MODE=compose needs baseData; use MODE=submissions for augment-only"
    exit 1
  fi
  ENDPOINT="$BASE/conf-templates/config"
fi

code=$(api -o "$tmp/resp.json" -w '%{http_code}' -X PUT "$ENDPOINT" \
  -H 'Content-Type: application/json' --data-binary @"$tmp/body.json")
if [ "$code" != "200" ]; then
  echo "::error::compose rejected (HTTP $code)"
  head -c 1200 "$tmp/resp.json"; echo
  exit 1
fi

message=$(jq -r '.message // ""' "$tmp/resp.json" 2>/dev/null || echo "")
if [ -n "$message" ]; then
  echo "::error::compose failed: $message"
  exit 1
fi

file_count=$(jq -r '((.config.configFiles.files // []) + (.config.auxFiles.files // [])) | length' "$tmp/resp.json")
if [ "$file_count" = "0" ]; then
  echo "::error::compose returned no config files"
  head -c 1200 "$tmp/resp.json"; echo
  exit 1
fi

# 5. hash, optionally compare/record, then write the tree + manifest
python3 - "$tmp/resp.json" "$OUT_DIR" "$ROOT_DIR" "$GROUP" "$INPUTS" \
  "$tmp/body.json" "$tmp/resolved.json" "$HASH_FILE" "$MODE" \
  "$DRY_RUN" "$HASH_ONLY" "$CHECK_HASH" "$WRITE_HASH" "$EXPECTED_SHA256" \
  "$NIM_MGMT_ENDPOINT" "$MGMT_PLACEHOLDER" <<'PY'
import base64, datetime, hashlib, json, pathlib, shutil, sys

(resp_path, out_dir, root_dir, group, inputs_path, body_path, resolved_path,
 hash_file, mode, dry_run, hash_only, check_hash, write_hash, expected_sha,
 mgmt_endpoint, mgmt_placeholder) = sys.argv[1:17]

def fail(message, code=1):
    print(message, file=sys.stderr)
    sys.exit(code)

# Reuse the canonical tree hash so `tree_hash.py` and `render.sh` agree.
sys.path.insert(0, str(pathlib.Path("scripts").resolve()))
from tree_hash import hash_files

resp = json.loads(pathlib.Path(resp_path).read_text())
out = pathlib.Path(out_dir)

def relative_name(name, root, managed_root):
    name = str(name).replace("\\", "/")
    if not root or root == "/":
        root = managed_root
    if name.startswith("/"):
        rd = (root or "").rstrip("/")
        if rd and (name == rd or name.startswith(rd + "/")):
            name = name[len(rd):]
        name = name.lstrip("/")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise SystemExit(f"refusing unsafe config path: {name!r}")
    return "/".join(parts)

# Every file returned by NIM, including every conf.d/*.conf and aux file.
files = {}
for section in ("configFiles", "auxFiles"):
    block = (resp.get("config") or {}).get(section) or {}
    section_root = block.get("rootDir") or root_dir
    for item in block.get("files") or []:
        rel = relative_name(item.get("name"), section_root or root_dir, root_dir)
        data = base64.b64decode(item.get("contents") or "")
        if rel in files and files[rel] != data:
            raise SystemExit(f"duplicate config path with different contents: {rel}")
        files[rel] = data

# Hash the placeholder tree first: this is the reviewed, endpoint-independent
# tree. Then substitute the real endpoint for the bytes we write and publish.
canonical = hash_files(files, strip_template_tags=True)
placeholder = mgmt_placeholder.encode()
endpoint = mgmt_endpoint.encode()
if endpoint:
    files = {rel: data.replace(placeholder, endpoint) for rel, data in files.items()}
elif any(placeholder in data for data in files.values()):
    fail(
        f"::error::rendered tree still contains {mgmt_placeholder!r}; "
        "set NIM_MGMT_ENDPOINT (or set mgmt_endpoint in the group inputs)",
        4,
    )
published = hash_files(files, strip_template_tags=True)
info = canonical
body_digest = hashlib.sha256(pathlib.Path(body_path).read_bytes()).hexdigest()
resolved = json.loads(pathlib.Path(resolved_path).read_text())
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

if expected_sha and expected_sha != info["sha256"]:
    fail(
        f"::error::rendered hash mismatch: expected {expected_sha}, "
        f"got {info['sha256']}",
        2,
    )

lock_path = pathlib.Path(hash_file)
lock = {}
if lock_path.exists():
    try:
        lock = json.loads(lock_path.read_text())
    except json.JSONDecodeError as exc:
        fail(f"::error::invalid hash file {lock_path}: {exc}")
    if not isinstance(lock, dict):
        fail(f"::error::hash file {lock_path} is not a JSON object")

entry = lock.get(group)
previous = entry.get("sha256") if isinstance(entry, dict) else None

if check_hash == "1":
    if not previous:
        fail(f"::error::no recorded render hash for {group} in {hash_file}", 3)
    if previous != info["sha256"]:
        fail(
            f"::error::rendered config changed for {group}: "
            f"{previous} -> {info['sha256']}",
            2,
        )
    print(f"render: group={group} unchanged sha256={info['sha256']}")

if write_hash == "1":
    lock[group] = {
        "sha256": info["sha256"],
        "crc32": info["crc32"],
        "files": info["files"],
        "bytes": info["bytes"],
        "inputs": inputs_path,
        "templates": resolved,
        "updatedAt": now,
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print(f"render: recorded {group} sha256={info['sha256']} in {hash_file}")

if hash_only == "1":
    print(f"sha256={info['sha256']}")
    print(f"crc32={info['crc32']}")
    print(f"files={info['files']}")
    print(f"bytes={info['bytes']}")
    sys.exit(0)

if dry_run == "1":
    print(
        f"render: group={group} mode={mode} files={info['files']} "
        f"sha256={info['sha256']} crc32={info['crc32']} (dry run, not written)"
    )
    for name in sorted(files):
        print(name)
    sys.exit(0)

if out.exists():
    shutil.rmtree(out)

for rel in sorted(files):
    dest = out / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(files[rel])

manifest = [
    f"rendered_at_utc={now}",
    f"group={group}",
    f"inputs={inputs_path}",
    f"root_dir={root_dir}",
    f"request_sha256={body_digest}",
    f"render_sha256={info['sha256']}",
    f"published_sha256={published['sha256']}",
    f"render_crc32={info['crc32']}",
    f"render_files={info['files']}",
    f"render_bytes={info['bytes']}",
    *[f"template={name}={uid}" for name, uid in sorted(resolved.items())],
    f"managed_files={info['files']}",
    *[f"file={name}" for name in sorted(files)],
]
(out / "render-manifest.txt").write_text("\n".join(manifest) + "\n")

print(
    f"render: group={group} files={info['files']} sha256={info['sha256']} "
    f"crc32={info['crc32']} out={out}"
)
for name in sorted(files):
    print(f"  {name}")
PY

# 6. optional lock update
if [ "$WRITE_LOCK" = "1" ]; then
  python3 - "$LOCK_FILE" "$tmp/resolved.json" <<'PY'
import json, pathlib, sys

lock_path, resolved_path = sys.argv[1:3]
p = pathlib.Path(lock_path)
lock = json.loads(p.read_text()) if p.exists() else {}
resolved = json.loads(pathlib.Path(resolved_path).read_text())
for name, uid in resolved.items():
    current = lock.get(name)
    if isinstance(current, dict):
        current["uid"] = uid
    else:
        lock[name] = {"uid": uid}
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
print(f"render: updated {lock_path}")
PY
fi
