#!/usr/bin/env bash
# Snapshot the CURRENT config of one instance group from NIM before publishing.
#
#   GROUP=template-cluster OUT_DIR=backup/template-cluster ./scripts/backup-config.sh
#
# This is the "real server" side: what the members are running now, as NIM holds
# it — not what this repo says. Uploaded as a workflow artifact so a bad publish
# can be rolled back with scripts/restore.sh. The mgmt endpoint is stored as a
# placeholder so the artifact contains no host.
set -euo pipefail

: "${NIM_URL:?set NIM_URL}"
: "${NIM_USER:?set NIM_USER}"
: "${NIM_PASSWORD:?set NIM_PASSWORD}"
: "${GROUP:?set GROUP (the group directory name)}"

cd "$(dirname "$0")/.."
if [ ! -d "groups/$GROUP" ]; then
  echo "::error::no such group directory: groups/$GROUP"
  exit 1
fi

OUT_DIR="${OUT_DIR:-backup/$GROUP}"
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

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

GROUP_UID=$(api "$BASE/instance-groups" \
  | jq -r --arg n "$GROUP" '.items[]? | select(.name==$n) | .uid' | head -1)
if [ -z "$GROUP_UID" ] || [ "$GROUP_UID" = "null" ]; then
  echo "::error::instance group '$GROUP' not found at $NIM_URL"
  exit 1
fi

api "$BASE/instance-groups/$GROUP_UID" > "$OUT_DIR/group.json"
api "$BASE/instance-groups/$GROUP_UID/config" > "$OUT_DIR/group-config.json"

NIM_MGMT_ENDPOINT="${NIM_MGMT_ENDPOINT:-}"
PLACEHOLDER="nim-mgmt-endpoint.invalid"

python3 - "$OUT_DIR" "$GROUP" "$GROUP_UID" "${EXTERNAL_ID:-unknown}" \
  "${EXTERNAL_ID_TYPE:-git}" "$NIM_MGMT_ENDPOINT" "$PLACEHOLDER" <<'PY'
import base64, datetime, hashlib, json, pathlib, re, sys

out_dir, group = sys.argv[1], sys.argv[2]
uid, trigger, trigger_type, endpoint, placeholder = sys.argv[3:8]
out = pathlib.Path(out_dir)
cfg = json.loads((out / "group-config.json").read_text())
group_doc = json.loads((out / "group.json").read_text())

ph = placeholder.encode()
usage = re.compile(rb"(usage_report[ \t]+endpoint=)([^;\s]+)")


def redact(data: bytes, name: str) -> bytes:
    # A backup is redacted, so be broad: the endpoint may also appear in a
    # proxy_pass, a comment or an upstream block. tree_hash.py stays narrow
    # because it compares against live config.
    found = [match.group(2) for match in usage.finditer(data)]
    if found and not endpoint:
        raise SystemExit(
            "::error::config contains the mgmt endpoint; set NIM_MGMT_ENDPOINT"
        )

    def repl(match) -> bytes:
        return match.group(1) + ph

    data = usage.sub(repl, data)
    needles = {value for value in found if value != ph}
    if endpoint:
        needles.add(endpoint.encode())
    for needle in needles:
        data = data.replace(needle, ph)

    for line in data.splitlines():
        if b"usage_report" in line and b"endpoint=" in line and ph not in line:
            raise SystemExit(f"::error::{name}: mgmt endpoint not redacted")
    for needle in needles:
        if needle and needle != ph and needle in data:
            raise SystemExit(f"::error::{name}: endpoint {needle!r} still present")
    return data


files = []
aux = []
for section in ("configFiles", "auxFiles"):
    for f in (cfg.get(section) or {}).get("files") or []:
        name = f["name"]
        data = base64.b64decode(f.get("contents") or "")
        if section == "auxFiles":
            # Aux is whatever NIM holds outside Git (certs, keys). It is not part
            # of the restore payload: restore.sh takes aux from the live group.
            # Keep only the name and digest, and never write the bytes to disk.
            f.pop("contents", None)
            f["sha256"] = hashlib.sha256(data).hexdigest()
            aux.append((name, f["sha256"]))
            continue
        data = redact(data, name)
        f["contents"] = base64.b64encode(data).decode()
        dest = out / name.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        files.append(name)

# The uploaded JSON is the authoritative restore payload; it must be redacted too.
(out / "group-config.json").write_text(json.dumps(cfg))

# group.json names the members and their instances; restore.sh does not need it.
members = len(group_doc.get("instances") or [])
(out / "group.json").unlink()

versions = ((group_doc.get("configVersion") or {}).get("versions") or [])
external = versions[-1].get("externalId") if versions else None

(out / "manifest.txt").write_text("\n".join([
    f"captured_at_utc={datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
    f"instance_group={group}",
    f"instance_group_uid={uid}",
    f"members={members}",
    f"group_config_update_time={cfg.get('updateTime')}",
    f"group_config_external_id={external or 'none'}",
    f"trigger_commit={trigger}",
    f"trigger_type={trigger_type}",
    f"managed_files={len(files)}",
    *[f"file={name}" for name in files],
    *[f"aux={name} sha256={digest}" for name, digest in aux],
]) + "\n")

print("\n".join([
    f"backup: group={group} uid={uid} members={members}",
    f"backup: externalId={external or 'none'} updateTime={cfg.get('updateTime')}",
    *[f"backup:   {name}" for name in files],
]))
PY

echo "backup: wrote $OUT_DIR ($(find "$OUT_DIR" -type f | wc -l | tr -d ' ') files)"
