#!/usr/bin/env bash
# Print the changed group directories of one mode, or "-" when none changed.
#
#   detect-groups.sh static "$BEFORE" "$SHA" "$EVENT"
#   detect-groups.sh template "" "" workflow_dispatch
#
# Fail closed: a directory without group.yaml is skipped, and an unknown
# deploy_mode is an error rather than a default.
set -euo pipefail

mode="${1:?usage: detect-groups.sh MODE BEFORE SHA EVENT}"
before="${2:-}"
sha="${3:-}"
event="${4:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$REPO_ROOT"

case "$mode" in
  static|template) ;;
  *) echo "::error::bad mode '$mode'" >&2; exit 2 ;;
esac

emit() {
  local d m
  for d in "$@"; do
    [ -n "$d" ] || continue
    [ -f "groups/$d/group.yaml" ] || continue
    m=$("$SCRIPT_DIR/group-mode.sh" "groups/$d") || return 2
    if [ "$m" = "$mode" ]; then printf '%s\n' "$d"; fi
  done
}

# A push whose `before` is unknown (history rewrite, force-push, fresh clone)
# cannot be diffed; treat it as "everything changed" rather than failing.
if [ "$event" = "push" ] && [ -n "$before" ] && \
   [ "$before" != "0000000000000000000000000000000000000000" ] && \
   ! git cat-file -e "$before^{commit}" 2>/dev/null; then
  echo "detect: before=$before is unknown; selecting every group" >&2
  before=""
fi

if [ "$event" != "push" ] || [ -z "$before" ] || \
   [ "$before" = "0000000000000000000000000000000000000000" ]; then
  groups=$("$SCRIPT_DIR/list-groups.sh" "$mode") || exit 2
  # shellcheck disable=SC2086
  out=$(emit $groups) || exit 2
else
  if [ "$mode" = "template" ] && \
     git diff --name-only "$before" "$sha" | grep -qE '^(templates/|\.nim/)'; then
    out=$("$SCRIPT_DIR/list-groups.sh" template) || exit 2
  else
    changed=$(git diff --name-only "$before" "$sha" -- groups/ \
      | awk -F/ 'NF >= 2 && $1 == "groups" && $2 != "" { print $2 }' | sort -u)
    # shellcheck disable=SC2086
    out=$(emit $changed) || exit 2
  fi
fi

if [ -z "$out" ]; then echo "-"; else printf '%s\n' "$out"; fi
