#!/usr/bin/env bash
# Snapshot the CURRENT instance-group config from NIM before publishing over it.
#
# This is the "real server" side of the config: what the instances are running
# right now (verified identical to the live /etc/nginx on the VMs), not what is
# in this repo. It is uploaded as a workflow artifact so a bad publish can be
# rolled back by re-publishing the captured tree.
set -euo pipefail

: "${NIM_URL:?set NIM_URL}"
: "${NIM_USER:?set NIM_USER}"
: "${NIM_PASSWORD:?set NIM_PASSWORD}"
: "${NIM_GROUP:?set NIM_GROUP}"

cd "$(dirname "$0")/.."
OUT_DIR="${OUT_DIR:-backup}"
BASE="${NIM_URL%/}/api/platform/v1"
api() { curl -sk -m 30 -u "$NIM_USER:$NIM_PASSWORD" "$@"; }

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

GROUP_UID=$(api "$BASE/instance-groups" \
  | jq -r --arg n "$NIM_GROUP" '.items[]? | select(.name==$n) | .uid' | head -1)
if [ -z "$GROUP_UID" ] || [ "$GROUP_UID" = "null" ]; then
  echo "::error::instance group '$NIM_GROUP' not found at $NIM_URL"
  exit 1
fi

api "$BASE/instance-groups/$GROUP_UID" > "$OUT_DIR/group.json"
api "$BASE/instance-groups/$GROUP_UID/config" > "$OUT_DIR/group-config.json"

python3 - "$OUT_DIR" "$NIM_URL" "$NIM_GROUP" "$GROUP_UID" "${EXTERNAL_ID:-unknown}" <<'PY'
import base64, json, pathlib, sys, datetime
out_dir, nim_url, group, uid, trigger = sys.argv[1:6]
out = pathlib.Path(out_dir)
cfg = json.loads((out / "group-config.json").read_text())
group_doc = json.loads((out / "group.json").read_text())

files = []
for section, root in (("configFiles", out / "etc"), ("auxFiles", out / "aux")):
    block = cfg.get(section) or {}
    for f in block.get("files") or []:
        dest = out / f["name"].lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(base64.b64decode(f["contents"]))
        files.append(f["name"])

versions = ((group_doc.get("configVersion") or {}).get("versions") or [])
external = versions[-1].get("externalId") if versions else None

(out / "manifest.txt").write_text("\n".join([
    f"captured_at_utc={datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
    f"nim_url={nim_url}",
    f"instance_group={group}",
    f"instance_group_uid={uid}",
    f"group_config_update_time={cfg.get('updateTime')}",
    f"group_config_external_id={external or 'none'}",
    f"trigger_commit={trigger}",
    f"managed_files={len(files)}",
    *[f"file={name}" for name in files],
]) + "\n")

print("\n".join([
    f"backup: group={group} uid={uid}",
    f"backup: externalId={external or 'none'} updateTime={cfg.get('updateTime')}",
    *[f"backup:   {name}" for name in files],
]))
PY

echo "backup: wrote $OUT_DIR ($(find "$OUT_DIR" -type f | wc -l | tr -d ' ') files)"
