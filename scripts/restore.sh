#!/usr/bin/env bash
# Re-publish a backup captured by backup-config.sh.
#
#   GROUP=template-cluster BACKUP_DIR=backup/template-cluster \
#     NIM_URL=https://manager-server NIM_USER=... NIM_PASSWORD=... \
#     NIM_MGMT_ENDPOINT=... ./scripts/restore.sh
#
# The backup's configFiles are stored with the mgmt endpoint replaced by
# nim-mgmt-endpoint.invalid. This script substitutes NIM_MGMT_ENDPOINT back
# before posting, so the artifact contains no host.
set -euo pipefail

: "${GROUP:?set GROUP}"
: "${BACKUP_DIR:?set BACKUP_DIR}"
: "${NIM_URL:?set NIM_URL}"
: "${NIM_USER:?set NIM_USER}"
: "${NIM_PASSWORD:?set NIM_PASSWORD}"
EXTERNAL_ID="${EXTERNAL_ID:-restore}"

cd "$(dirname "$0")/.."
BASE="${NIM_URL%/}/api/platform/v1"
NIM_CA="${NIM_CA:-certs/nim-ca.pem}"
PLACEHOLDER="nim-mgmt-endpoint.invalid"
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
    sleep $((attempt * 5))
  done
}

GROUP_UID=$(api "$BASE/instance-groups" \
  | jq -r --arg n "$GROUP" '.items[]? | select(.name==$n) | .uid' | head -1)
[ -n "$GROUP_UID" ] && [ "$GROUP_UID" != "null" ] || {
  echo "::error::instance group '$GROUP' not found"; exit 1; }

CURRENT=$(api "$BASE/instance-groups/$GROUP_UID/config")
LIVE_AUX=$(printf '%s' "$CURRENT" | jq -c '.auxFiles // {"rootDir":"/","files":[]}')
UPDATE_TIME=$(jq -r '.updateTime // .createTime' <<<"$CURRENT")

PAYLOAD=$(mktemp)
RESP=$(mktemp)
trap 'rm -f "$PAYLOAD" "$RESP"' EXIT

python3 - "$BACKUP_DIR" "$UPDATE_TIME" "$EXTERNAL_ID" "$PLACEHOLDER" \
  "${NIM_MGMT_ENDPOINT:-}" "$LIVE_AUX" > "$PAYLOAD" <<'PY'
import base64, hashlib, json, pathlib, sys

backup, update_time, external_id, placeholder, endpoint, live_aux = sys.argv[1:7]
src = json.loads((pathlib.Path(backup) / "group-config.json").read_text())
needle = placeholder.encode()
real = endpoint.encode()

def checked_aux(live, recorded):
    expected = {
        item.get("name"): item.get("sha256")
        for item in (recorded or {}).get("files") or []
        if item.get("sha256")
    }
    for item in live.get("files") or []:
        want = expected.get(item.get("name"))
        if not want:
            continue
        data = base64.b64decode(item.get("contents") or "")
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            raise SystemExit(
                f"::error::aux {item['name']} changed since the backup: {want} -> {got}"
            )
    return live


def fix(block):
    for item in (block or {}).get("files") or []:
        data = base64.b64decode(item.get("contents") or "")
        if real:
            data = data.replace(needle, real)
        elif needle in data:
            raise SystemExit(
                "::error::backup contains the endpoint placeholder; set NIM_MGMT_ENDPOINT"
            )
        item["contents"] = base64.b64encode(data).decode()
    return block

print(json.dumps({
    "updateTime": update_time,
    "configFiles": fix(src.get("configFiles")),
    # The artifact stores aux as name+sha256 only (certs and keys must not be
    # in a public artifact), so take the bytes from the group as it is now and
    # verify them against the recorded digest.
    "auxFiles": checked_aux(json.loads(live_aux), src.get("auxFiles")),
    "externalId": external_id,
    "externalIdType": "other",
}))
PY

code=$(api -o "$RESP" -w '%{http_code}' -X POST \
  "$BASE/instance-groups/$GROUP_UID/config" \
  -H 'Content-Type: application/json' -d @"$PAYLOAD")
case "$code" in
  200|202) ;;
  *) echo "::error::restore rejected (HTTP $code)"; head -c 800 "$RESP"; exit 1 ;;
esac

DEPLOY=$(jq -r '.deploymentUID' "$RESP")
sleep 3
seen=0
for _ in $(seq 1 40); do
  d=$(api "$BASE/instance-groups/deployments/$DEPLOY")
  pending=$(jq -r '(.details.pending // []) | length' <<<"$d")
  done_count=$(jq -r '((.details.success // []) | length) + ((.details.failure // []) | length)' <<<"$d")
  if [ "$pending" = "0" ] && [ "$done_count" -ge 1 ]; then seen=1; break; fi
  sleep 3
done

if [ "$seen" = "0" ]; then
  echo "::error::timed out waiting for restore deployment $DEPLOY"
  exit 1
fi

fail=$(jq -r '(.details.failure // []) | length' <<<"$d")
err=$(jq -r '.details.error // ""' <<<"$d")
if [ "$fail" != "0" ] || [ -n "$err" ]; then
  jq '{status, success: (.details.success|length), failure: (.details.failure|length), error}' <<<"$d"
  exit 1
fi
echo "restore: group=$GROUP deployment=$DEPLOY applied"
