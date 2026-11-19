#!/usr/bin/env bash
# Publish groups/<GROUP>/ to the NIM instance group <GROUP>.
#
#   GROUP=docker-plus-cluster ./scripts/publish.sh
#
# The payload is declarative for the files NIM manages on that group: omitting a
# file that was published before DELETES it on the members. Each group tree must
# therefore carry every file the group owns — including ones the image also ships
# (e.g. conf.d/plus-api.conf), because those ARE managed once published.
set -euo pipefail

: "${NIM_URL:?set NIM_URL}"
: "${NIM_USER:?set NIM_USER}"
: "${NIM_PASSWORD:?set NIM_PASSWORD}"
: "${GROUP:?set GROUP (the group directory name)}"

cd "$(dirname "$0")/.."
CONFIG_DIR="groups/$GROUP"
ROOT_DIR="${ROOT_DIR:-/etc/nginx}"
if [ ! -d "$CONFIG_DIR" ]; then
  echo "::error::no such group directory: $CONFIG_DIR"
  exit 1
fi

EXTERNAL_ID="${EXTERNAL_ID:-$(git rev-parse HEAD 2>/dev/null || echo manual)}"
BASE="${NIM_URL%/}/api/platform/v1"
api() { curl -sk -m 30 -u "$NIM_USER:$NIM_PASSWORD" "$@"; }

group_doc=$(api "$BASE/instance-groups")
GROUP_UID=$(jq -r --arg n "$GROUP" '.items[]? | select(.name==$n) | .uid' <<<"$group_doc" | head -1)
if [ -z "$GROUP_UID" ] || [ "$GROUP_UID" = "null" ]; then
  echo "::error::instance group '$GROUP' not found at $NIM_URL"
  exit 1
fi
MEMBERS=$(jq -r --arg n "$GROUP" '[.items[]? | select(.name==$n) | (.instances // []) | length][0] // 0' <<<"$group_doc")

UPDATE_TIME=$(api "$BASE/instance-groups/$GROUP_UID/config" | jq -r '.updateTime // .createTime')
[ -n "$UPDATE_TIME" ] && [ "$UPDATE_TIME" != "null" ] || { echo "::error::could not read group config updateTime"; exit 1; }

python3 - "$CONFIG_DIR" "$ROOT_DIR" "$UPDATE_TIME" "$EXTERNAL_ID" > /tmp/payload.json <<'PY'
import base64, json, os, sys
config_dir, root, update_time, external_id = sys.argv[1:5]
files = []
for dirpath, _, names in os.walk(config_dir):
    for name in names:
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, config_dir).replace(os.sep, "/")
        if rel == "group.yaml":
            continue
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

echo "group=$GROUP ($GROUP_UID) members=$MEMBERS files=$(jq '.configFiles.files|length' /tmp/payload.json) externalId=$EXTERNAL_ID"
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

# A fresh deployment record exists before its details are populated, so wait for
# at least one recorded outcome as well as pending == 0.
sleep 3
seen=0
for _ in $(seq 1 40); do
  deployment=$(api "$BASE/instance-groups/deployments/$DEPLOY")
  pending=$(jq -r '(.details.pending // []) | length' <<<"$deployment")
  finished=$(jq -r '((.details.success // []) | length) + ((.details.failure // []) | length)' <<<"$deployment")
  if [ "$pending" = "0" ] && [ "$finished" -ge 1 ]; then seen=1; break; fi
  sleep 3
done

if [ "$seen" = "0" ]; then
  if [ "$MEMBERS" = "0" ]; then
    echo "group has no members yet; config stored for future members (deployment $DEPLOY)"
    exit 0
  fi
  echo "::error::timed out waiting for deployment $DEPLOY — no instance reported an outcome (are the members offline?)"
  exit 1
fi

ok=$(jq -r '(.details.success // []) | length' <<<"$deployment")
fail=$(jq -r '(.details.failure // []) | length' <<<"$deployment")
err=$(jq -r '.details.error // ""' <<<"$deployment")
jq '{status, success: (.details.success|length), failure: (.details.failure|length), pending: (.details.pending|length), error: (.details.error // "")}' <<<"$deployment"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### Published to \`$GROUP\`"
    echo
    echo "| field | value |"
    echo "|---|---|"
    echo "| externalId | \`$EXTERNAL_ID\` |"
    echo "| deployment | \`$DEPLOY\` |"
    echo "| members | $MEMBERS |"
    echo "| success / failure / pending | $(jq -r '"\(.details.success|length) / \(.details.failure|length) / \(.details.pending|length)"' <<<"$deployment") |"
    echo
    echo "Files:"
    echo '```'
    jq -r '.configFiles.files[].name' /tmp/payload.json
    echo '```'
  } >> "$GITHUB_STEP_SUMMARY"
fi

if [ "$fail" != "0" ]; then
  echo "::error::$fail instance(s) failed to apply the config"
  jq -r '.details.failure[]' <<<"$deployment" | head -20
  exit 1
fi
if [ -n "$err" ]; then
  echo "::error::deployment error: $err"
  exit 1
fi
if [ "$ok" = "0" ] && [ "$MEMBERS" != "0" ]; then
  echo "::error::no instance applied the config"
  exit 1
fi

echo "ok: $ok instance(s) applied externalId=$EXTERNAL_ID (members=$MEMBERS)"
