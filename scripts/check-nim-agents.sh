#!/usr/bin/env bash
# Fail if any NIM system is not online.
#
#   NIM_URL=... NIM_USER=... NIM_PASSWORD=... ./scripts/check-nim-agents.sh
#
# Exit: 0 all online, 1 no systems returned, 2 one or more offline.
set -euo pipefail

: "${NIM_URL:?set NIM_URL}"
: "${NIM_USER:?set NIM_USER}"
: "${NIM_PASSWORD:?set NIM_PASSWORD}"

BASE="${NIM_URL%/}/api/platform/v1"
api() {
  local attempt rc
  for attempt in 1 2 3; do
    if curl -sk -m 30 -u "$NIM_USER:$NIM_PASSWORD" "$@"; then return 0; fi
    rc=$?
    if [ "$attempt" -eq 3 ]; then return "$rc"; fi
    echo "api: attempt $attempt failed (curl $rc); retrying in $((attempt * 5))s" >&2
    sleep $((attempt * 5))
  done
}

systems=$(api "$BASE/systems")
count=$(jq -r '(.items // []) | length' <<<"$systems")
if [ "$count" -eq 0 ]; then
  echo "::error::NIM returned no systems"
  exit 1
fi

jq -r '.items[] | [.hostname, (.status.state // "unknown"), (.status.lastStatusReport // "")] | @tsv' <<<"$systems" \
  | sed 's/^/agent: /'

offline=$(jq -r '[.items[] | select((.status.state // "unknown") != "online")] | length' <<<"$systems")
if [ "$offline" -gt 0 ]; then
  echo "::error::$offline of $count NIM system(s) not online"
  exit 2
fi

echo "agents: all $count online"
