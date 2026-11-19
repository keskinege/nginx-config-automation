#!/usr/bin/env bash
# Publish config/ to the NIM instance group as its group config.
#
# The payload is declarative for the files NIM manages: omitting a file that was
# published before DELETES it on the members. Files shipped by the image (e.g.
# conf.d/plus-api.conf in the Plus container) are not managed and are left alone.
set -euo pipefail

: "${NIM_URL:?set NIM_URL (e.g. https://<nim-host>)}"
: "${NIM_USER:?set NIM_USER}"
: "${NIM_PASSWORD:?set NIM_PASSWORD}"
: "${NIM_GROUP:?set NIM_GROUP (instance group name)}"

cd "$(dirname "$0")/.."

ROOT_DIR="${ROOT_DIR:-/etc/nginx}"
EXTERNAL_ID="${EXTERNAL_ID:-$(git rev-parse HEAD 2>/dev/null || echo manual)}"
BASE="${NIM_URL%/}/api/platform/v1"

api() { curl -sk -m 30 -u "$NIM_USER:$NIM_PASSWORD" "$@"; }

GROUP_UID=$(api "$BASE/instance-groups" \
  | jq -r --arg n "$NIM_GROUP" '.items[]? | select(.name==$n) | .uid' | head -1)
if [ -z "$GROUP_UID" ] || [ "$GROUP_UID" = "null" ]; then
  echo "::error::instance group '$NIM_GROUP' not found at $NIM_URL"
  exit 1
fi

UPDATE_TIME=$(api "$BASE/instance-groups/$GROUP_UID/config" | jq -r '.updateTime // .createTime')
[ -n "$UPDATE_TIME" ] && [ "$UPDATE_TIME" != "null" ] || { echo "::error::could not read group config updateTime"; exit 1; }

python3 - "$ROOT_DIR" "$UPDATE_TIME" "$EXTERNAL_ID" > /tmp/payload.json <<'PY'
import base64, json, os, sys
root, update_time, external_id = sys.argv[1:4]
files = []
for dirpath, _, names in os.walk("config"):
    for name in names:
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, "config").replace(os.sep, "/")
        files.append({
            "name": f"{root}/{rel}",
            "contents": base64.b64encode(open(full, "rb").read()).decode(),
        })
files.sort(key=lambda f: f["name"])
print(json.dumps({
    "updateTime": update_time,
    "configFiles": {"rootDir": root, "files": files},
    "auxFiles": {"rootDir": "/", "files": []},
    "externalId": external_id,
    "externalIdType": "git",
}))
PY

echo "group=$NIM_GROUP ($GROUP_UID) files=$(jq '.configFiles.files|length' /tmp/payload.json) externalId=$EXTERNAL_ID"
jq -r '.configFiles.files[].name' /tmp/payload.json | sed 's/^/  /'

resp=$(mktemp)
code=$(api -o "$resp" -w '%{http_code}' -X POST \
  "$BASE/instance-groups/$GROUP_UID/config" \
  -H 'Content-Type: application/json' -d @/tmp/payload.json)

if [ "$code" != "202" ] && [ "$code" != "200" ]; then
  echo "::error::publish rejected (HTTP $code)"
  head -c 800 "$resp"; echo
  exit 1
fi

DEPLOY=$(jq -r '.deploymentUID' "$resp")
echo "deployment=$DEPLOY"

# Poll until nothing is pending (bounded).
for _ in $(seq 1 40); do
  deployment=$(api "$BASE/instance-groups/deployments/$DEPLOY")
  pending=$(jq -r '(.details.pending // []) | length' <<<"$deployment")
  [ "$pending" = "0" ] && break
  sleep 3
done

jq '{status, success: (.details.success|length), failure: (.details.failure|length), pending: (.details.pending|length), error: (.details.error // "")}' <<<"$deployment" | tee /tmp/deployment.json

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### Published to \`$NIM_GROUP\`"
    echo
    echo "| field | value |"
    echo "|---|---|"
    echo "| externalId | \`$EXTERNAL_ID\` |"
    echo "| deployment | \`$DEPLOY\` |"
    echo "| success / failure / pending | $(jq -r '"\(.details.success|length) / \(.details.failure|length) / \(.details.pending|length)"' <<<"$deployment") |"
    echo
    echo "Files:"
    echo '```'
    jq -r '.configFiles.files[].name' /tmp/payload.json
    echo '```'
  } >> "$GITHUB_STEP_SUMMARY"
fi

fail=$(jq -r '(.details.failure // []) | length' <<<"$deployment")
ok=$(jq -r '(.details.success // []) | length' <<<"$deployment")
err=$(jq -r '.details.error // ""' <<<"$deployment")

if [ "$fail" != "0" ]; then
  echo "::error::$fail instance(s) failed to apply the config"
  jq -r '.details.failure[]' <<<"$deployment" | head -20
  exit 1
fi
if [ -n "$err" ]; then
  echo "::error::deployment error: $err"
  exit 1
fi
if [ "$ok" = "0" ]; then
  echo "::error::no instance applied the config (all offline?)"
  exit 1
fi

echo "ok: $ok instance(s) applied externalId=$EXTERNAL_ID"
