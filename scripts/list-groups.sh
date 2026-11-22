#!/usr/bin/env bash
# List groups whose deploy_mode matches $1 (default: all).
set -euo pipefail
cd "$(dirname "$0")/.."
GROUPS_DIR="${GROUPS_DIR:-groups}"
MODE="${1:-}"
for gdir in "$GROUPS_DIR"/*/; do
  [ -f "$gdir/group.yaml" ] || continue
  mode=$(yq -r '.deploy_mode // "static"' "$gdir/group.yaml")
  if [ -z "$MODE" ] || [ "$mode" = "$MODE" ]; then
    basename "$gdir"
  fi
done
