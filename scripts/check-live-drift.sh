#!/usr/bin/env bash
# Compare the live NIM group config to the recorded rendered hash.
#
#   GROUP=static-cluster NIM_URL=... NIM_USER=... NIM_PASSWORD=... \
#     ./scripts/check-live-drift.sh
#
# Exit codes: 0 no drift, 2 drift, 3 no recorded hash.
set -euo pipefail

: "${GROUP:?set GROUP (the group directory name)}"
: "${NIM_URL:?set NIM_URL}"
: "${NIM_USER:?set NIM_USER}"
: "${NIM_PASSWORD:?set NIM_PASSWORD}"

cd "$(dirname "$0")/.."
HASH_FILE="${HASH_FILE:-.nim/rendered.lock.json}"
ROOT_DIR="${ROOT_DIR:-/etc/nginx}"
BASE="${NIM_URL%/}/api/platform/v1"
NIM_CA="${NIM_CA:-certs/nim-ca.pem}"
CURL=(curl -sS -m 30 --cacert "$NIM_CA" -u "$NIM_USER:$NIM_PASSWORD")
if [ -n "${NIM_HOST:-}" ]; then
  CURL+=(--resolve "manager-server:443:$NIM_HOST")
fi

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

GROUP_UID=$(api "$BASE/instance-groups" \
  | jq -r --arg n "$GROUP" '.items[]? | select(.name==$n) | .uid' | head -1)
if [ -z "$GROUP_UID" ] || [ "$GROUP_UID" = "null" ]; then
  echo "::error::instance group '$GROUP' not found at $NIM_URL"
  exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

api "$BASE/instance-groups/$GROUP_UID/config" > "$tmp/live.json"
python3 - "$tmp/live.json" "$tmp/tree" "$ROOT_DIR" <<'PY'
import base64, json, pathlib, sys

src, out, managed_root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
data = json.loads(src.read_text())

def relative_name(name, root):
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

for section in ("configFiles",):
    # auxFiles are preserved from the live group (e.g. tls/tls.crt) and are
    # outside the Git-declarative set, so they are not part of this hash.
    block = (data.get(section) or {})
    section_root = block.get("rootDir") or managed_root
    for item in block.get("files") or []:
        rel = relative_name(item.get("name"), section_root)
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(base64.b64decode(item.get("contents") or ""))
print(f"live files: {sum(1 for p in out.rglob('*') if p.is_file())}")
PY

live=$(python3 scripts/tree_hash.py "$tmp/tree" --strip-template-tags \
  --normalize-endpoint "${NIM_MGMT_ENDPOINT:?set NIM_MGMT_ENDPOINT}" \
  | awk -F= '/^sha256=/{print $2}')
if ! expected=$(python3 - "$HASH_FILE" "$GROUP" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
if not path.exists():
    raise SystemExit(3)
lock = json.loads(path.read_text())
entry = lock.get(sys.argv[2])
if not isinstance(entry, dict) or not entry.get("sha256"):
    raise SystemExit(3)
print(entry["sha256"])
PY
); then
  echo "::error::no recorded render hash for $GROUP in $HASH_FILE"
  exit 3
fi

if [ "$live" != "$expected" ]; then
  echo "::error::live config drift for $GROUP: expected $expected, live $live"
  exit 2
fi
echo "drift: none group=$GROUP sha256=$live"
