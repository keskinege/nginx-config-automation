#!/usr/bin/env bash
# List groups whose deploy_mode matches $1 (default: all).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$REPO_ROOT"
GROUPS_DIR="${GROUPS_DIR:-groups}"
MODE="${1:-}"
for gdir in "$GROUPS_DIR"/*/; do
  [ -f "$gdir/group.yaml" ] || continue
  mode=$("$SCRIPT_DIR/group-mode.sh" "${gdir%/}")
  if [ -z "$MODE" ] || [ "$mode" = "$MODE" ]; then
    basename "$gdir"
  fi
done
