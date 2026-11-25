#!/usr/bin/env bash
# Publish groups/<GROUP>/ to the NIM instance group <GROUP>.
#
#   GROUP=static-cluster ./scripts/publish.sh
#
# The payload is declarative for the files NIM manages on that group: omitting a
# file that was published before DELETES it on the members. Every file in
# CONFIG_DIR is managed; a file the image also ships (e.g. conf.d/plus-api.conf)
# must be in CONFIG_DIR if you intend to own it.
set -euo pipefail

: "${NIM_URL:?set NIM_URL}"
: "${NIM_USER:?set NIM_USER}"
: "${NIM_PASSWORD:?set NIM_PASSWORD}"
: "${GROUP:?set GROUP (the group directory name)}"

cd "$(dirname "$0")/.."
CONFIG_DIR="${CONFIG_DIR:-groups/$GROUP}"
ROOT_DIR="${ROOT_DIR:-/etc/nginx}"
if [ ! -d "$CONFIG_DIR" ]; then
  echo "::error::no such config directory: $CONFIG_DIR"
  exit 1
fi

EXTERNAL_ID="${EXTERNAL_ID:-$(git rev-parse HEAD 2>/dev/null || echo manual)}"
EXTERNAL_ID_TYPE="${EXTERNAL_ID_TYPE:-git}"
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

group_doc=$(api "$BASE/instance-groups")
GROUP_UID=$(jq -r --arg n "$GROUP" '.items[]? | select(.name==$n) | .uid' <<<"$group_doc" | head -1)
if [ -z "$GROUP_UID" ] || [ "$GROUP_UID" = "null" ]; then
  echo "::error::instance group '$GROUP' not found at $NIM_URL"
  exit 1
fi
MEMBERS=$(jq -r --arg n "$GROUP" '[.items[]? | select(.name==$n) | (.instances // []) | length][0] // 0' <<<"$group_doc")
if [ "$MEMBERS" = "0" ]; then
  # The list endpoint may omit instances; the group document carries them.
  # (/instance-groups/<uid>/instances returns HTTP 400 on the real NIM.)
  doc=$(api "$BASE/instance-groups/$GROUP_UID" || true)
  if jq -e 'has("instances")' >/dev/null 2>&1 <<<"$doc"; then
    MEMBERS=$(jq -r '(.instances // []) | length' <<<"$doc")
  fi
fi

CURRENT_CONFIG=$(api "$BASE/instance-groups/$GROUP_UID/config")
UPDATE_TIME=$(jq -r '.updateTime // .createTime' <<<"$CURRENT_CONFIG")
[ -n "$UPDATE_TIME" ] && [ "$UPDATE_TIME" != "null" ] || { echo "::error::could not read group config updateTime"; exit 1; }

PRESERVE_AUX="${PRESERVE_AUX:-0}"
# Replace the documented mgmt-endpoint placeholder before the payload is sent.
# Required whenever a file still contains it; set MGMT_PLACEHOLDER to override.
NIM_MGMT_ENDPOINT="${NIM_MGMT_ENDPOINT:-}"
MGMT_PLACEHOLDER="${MGMT_PLACEHOLDER:-nim-mgmt-endpoint.invalid}"
if [ "$PRESERVE_AUX" = "1" ]; then
  AUX_FILES=$(jq -c '.auxFiles // {"rootDir":"/","files":[]}' <<<"$CURRENT_CONFIG")
else
  AUX_FILES='{"rootDir":"/","files":[]}'
fi

PAYLOAD=$(mktemp)
trap 'rm -f "$PAYLOAD"' EXIT
python3 - "$CONFIG_DIR" "$ROOT_DIR" "$UPDATE_TIME" "$EXTERNAL_ID" "$EXTERNAL_ID_TYPE" "$AUX_FILES" \
  "$NIM_MGMT_ENDPOINT" "$MGMT_PLACEHOLDER" > "$PAYLOAD" <<'PY'
import base64, json, os, sys
sys.path.insert(0, "scripts")
from select_files import managed
(config_dir, root, update_time, external_id, external_id_type, aux_json,
 mgmt_endpoint, mgmt_placeholder) = sys.argv[1:9]
placeholder = mgmt_placeholder.encode()
endpoint = mgmt_endpoint.encode()
files = []
for dirpath, dirnames, names in os.walk(config_dir):
    dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
    for name in names:
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, config_dir).replace(os.sep, "/")
        if not managed(rel):
            continue
        data = open(full, "rb").read()
        if endpoint:
            data = data.replace(placeholder, endpoint)
        elif placeholder in data:
            raise SystemExit(
                f"::error::{rel} still contains {mgmt_placeholder!r}; "
                "set NIM_MGMT_ENDPOINT (or MGMT_PLACEHOLDER)"
            )
        files.append({
            "name": f"{root}/{rel}",
            "contents": base64.b64encode(data).decode(),
        })
files.sort(key=lambda f: f["name"])
print(json.dumps({
    "updateTime": update_time,
    "configFiles": {"rootDir": root, "files": files},
    "auxFiles": json.loads(aux_json),
    "externalId": external_id,
    "externalIdType": external_id_type,
}))
PY

echo "group=$GROUP ($GROUP_UID) members=$MEMBERS files=$(jq '.configFiles.files|length' "$PAYLOAD") aux=$(jq '.auxFiles.files|length' "$PAYLOAD") externalId=$EXTERNAL_ID"
jq -r '.configFiles.files[].name' "$PAYLOAD" | sed 's/^/  /'

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "publish: group=$GROUP config_dir=$CONFIG_DIR files=$(jq '.configFiles.files|length' "$PAYLOAD") externalId=$EXTERNAL_ID (dry run)"
  echo "payload=$PAYLOAD"
  jq -r '.configFiles.files[].name' "$PAYLOAD" | sed 's/^/  /'
  trap - EXIT
  exit 0
fi

resp=$(mktemp)
# Never retry the POST: a retry after a timeout sends a stale updateTime and
# gets 412 even though the first attempt applied the config. On a transport
# error, ask NIM whether this externalId is already stored.
rc=0
code=$("${CURL[@]}" -o "$resp" -w '%{http_code}' -X POST \
  "$BASE/instance-groups/$GROUP_UID/config" \
  -H 'Content-Type: application/json' -d @"$PAYLOAD") || rc=$?

if [ "$rc" != "0" ]; then
  echo "::warning::publish POST failed at the transport level (curl $rc); not retrying"
  doc=$(api "$BASE/instance-groups/$GROUP_UID") || true
  if jq -e --arg e "$EXTERNAL_ID" \
      '[(.configVersion.versions // [])[].externalId] | index($e)' \
      <<<"$doc" >/dev/null 2>&1; then
    DEPLOY=$(jq -r '.lastDeploymentDetails.id // empty' <<<"$doc")
    echo "publish: externalId=$EXTERNAL_ID is stored despite the transport error"
    if [ -z "$DEPLOY" ]; then
      echo "ok: externalId=$EXTERNAL_ID stored (no deployment id reported)"
      exit 0
    fi
  else
    echo "::error::publish POST failed (curl $rc) and externalId=$EXTERNAL_ID is not stored"
    exit 1
  fi
elif [ "$code" != "202" ] && [ "$code" != "200" ]; then
  echo "::error::publish rejected (HTTP $code)"
  head -c 800 "$resp"; echo
  exit 1
else
  DEPLOY=$(jq -r '.deploymentUID' "$resp")
fi

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
    jq -r '.configFiles.files[].name' "$PAYLOAD"
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
finished=$((ok + fail))
if [ "$MEMBERS" != "0" ] && [ "$finished" -lt "$MEMBERS" ] && [ "${ALLOW_PARTIAL:-0}" != "1" ]; then
  echo "::error::$((MEMBERS - finished)) of $MEMBERS member(s) did not report an outcome; set ALLOW_PARTIAL=1 to accept a partial apply"
  exit 1
fi

echo "ok: $ok instance(s) applied externalId=$EXTERNAL_ID (members=$MEMBERS)"
