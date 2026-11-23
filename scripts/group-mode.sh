#!/usr/bin/env bash
# Print the deploy_mode of one group directory. Fail closed.
#
#   scripts/group-mode.sh groups/static-cluster   # -> static
#
# Exit 2 when group.yaml is missing or deploy_mode is not static|template.
set -euo pipefail

d="${1:?usage: group-mode.sh GROUPS_DIR/GROUP}"
f="$d/group.yaml"
if [ ! -f "$f" ]; then
  echo "::error file=$f::missing group.yaml" >&2
  exit 2
fi

mode=$(yq -r '.deploy_mode // "static"' "$f")
case "$mode" in
  static|template) printf '%s\n' "$mode" ;;
  *)
    echo "::error file=$f::deploy_mode must be 'static' or 'template', got '$mode'" >&2
    exit 2
    ;;
esac
