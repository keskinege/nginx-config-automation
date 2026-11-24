#!/usr/bin/env bash
# Lint every group tree under groups/<group>/ for the invariants NIM and the
# Plus image depend on. A group is a directory whose name is the NIM instance
# group name, carrying a group.yaml with its metadata.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$REPO_ROOT"
rc=0
shopt -s nullglob

if [ "${1:-}" = "--rendered" ]; then
  g="${2:?usage: lint.sh --rendered GROUP}"
  gdir="groups/$g"
  [ -f "$gdir/group.yaml" ] || { echo "::error::no group $g"; exit 2; }
  [ -d "rendered/$g" ] || { echo "::error::no rendered/$g"; exit 2; }
  require_mgmt=$(yq -r '.require_mgmt // false' "$gdir/group.yaml")
  input_mgmt=$(yq -r '.baseData.main.templateInput.require_mgmt // false' "$gdir/inputs.yaml" 2>/dev/null || true)
  if [ -n "$input_mgmt" ] && [ "$input_mgmt" != "$require_mgmt" ]; then
    echo "::error file=$gdir/inputs.yaml::require_mgmt $input_mgmt does not match group.yaml $require_mgmt"
    exit 1
  fi
  rc=0
  if ! grep -qE '^[[:space:]]*include[[:space:]]+/etc/nginx/conf\.d/\*\.conf;' "rendered/$g/nginx.conf"; then
    echo "::error file=rendered/$g/nginx.conf::must include /etc/nginx/conf.d/*.conf"; rc=1
  fi
  if [ "$require_mgmt" = "true" ] && ! grep -qE '^mgmt[[:space:]]*\{' "rendered/$g/nginx.conf"; then
    echo "::error file=rendered/$g/nginx.conf::must keep the mgmt block"; rc=1
  fi
  servers=$(grep -rnE 'listen[[:space:]]+80\b' "rendered/$g" | wc -l | tr -d ' ')
  defaults=$(grep -rnE 'listen[[:space:]]+80[[:space:]]+default_server' "rendered/$g" | wc -l | tr -d ' ')
  if [ "$servers" -gt 0 ] && [ "$defaults" -eq 0 ]; then
    echo "::error::a :80 server exists but none is default_server"; rc=1
  fi
  if [ "$defaults" -gt 1 ]; then
    echo "::error::more than one 'listen 80 default_server'"; rc=1
  fi
  [ "$rc" -eq 0 ] && echo "lint: rendered/$g ok"
  exit "$rc"
fi

ONLY=""
if [ "${1:-}" = "--group" ]; then
  ONLY="${2:?usage: lint.sh --group GROUP}"
  [ -f "groups/$ONLY/group.yaml" ] || { echo "::error::no group $ONLY"; exit 2; }
fi

if [ -n "$ONLY" ]; then
  if [ -f "groups/$ONLY/inputs.yaml" ]; then
    python3 "$SCRIPT_DIR/lint-inputs.py" "groups/$ONLY/inputs.yaml" || rc=1
  fi
elif compgen -G "groups/*/inputs.yaml" >/dev/null; then
  python3 "$SCRIPT_DIR/lint-inputs.py" groups/*/inputs.yaml || rc=1
fi

for gdir in groups/*/; do
  g=$(basename "$gdir")
  [ -z "$ONLY" ] || [ "$ONLY" = "$g" ] || continue
  grc=0
  mode=$("$SCRIPT_DIR/group-mode.sh" "${gdir%/}")
  if [ "$mode" = template ]; then
    echo "lint: $g skipped (template)"
    continue
  fi

  if [ ! -f "$gdir/nginx.conf" ]; then
    echo "::error file=$gdir::missing nginx.conf"
    rc=1
    continue
  fi

  declared=$(yq -r '.name // ""' "$gdir/group.yaml")
  if [ "$declared" != "$g" ]; then
    echo "::error file=$gdir/group.yaml::name '$declared' does not match directory '$g'"
    grc=1
  fi

  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    echo "::error::tab character: $hit"
    grc=1
  done < <(grep -rn $'\t' "$gdir" || true)

  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    echo "::error::trailing whitespace: $hit"
    grc=1
  done < <(grep -rnE ' +$' "$gdir" || true)

  if ! grep -qE '^[[:space:]]*include[[:space:]]+/etc/nginx/conf\.d/\*\.conf;' "$gdir/nginx.conf"; then
    echo "::error file=$gdir/nginx.conf::must include /etc/nginx/conf.d/*.conf"
    grc=1
  fi

  while IFS= read -r inc; do
    [ -n "$inc" ] || continue
    rel=${inc#/etc/nginx/}
    if [ ! -f "$gdir/$rel" ]; then
      echo "::error file=${gdir%/}/nginx.conf::include $inc is not present in the group tree"
      grc=1
    fi
  done < <(grep -rhoE '^[[:space:]]*include[[:space:]]+/etc/nginx/[^;*]+;' "$gdir/nginx.conf" \
    | sed -E 's/^[[:space:]]*include[[:space:]]+//; s/;$//')

  require_mgmt=$(yq -r '.require_mgmt // false' "$gdir/group.yaml")
  if [ "$require_mgmt" = "true" ] && ! grep -qE '^mgmt[[:space:]]*\{' "$gdir/nginx.conf"; then
    echo "::error file=$gdir/nginx.conf::must keep the mgmt { usage_report ... } block (main context)"
    grc=1
  fi

  servers=$(grep -rnE 'listen[[:space:]]+80\b' "$gdir" | wc -l | tr -d ' ')
  defaults=$(grep -rnE 'listen[[:space:]]+80[[:space:]]+default_server' "$gdir" | wc -l | tr -d ' ')
  if [ "$servers" -gt 0 ] && [ "$defaults" -eq 0 ]; then
    echo "::error file=$gdir::a :80 server exists but none is default_server"
    grc=1
  fi
  if [ "$defaults" -gt 1 ]; then
    echo "::error file=$gdir::more than one 'listen 80 default_server' in the tree"
    grc=1
  fi

  if [ "$grc" -eq 0 ]; then
    echo "lint: $g ok"
  else
    rc=1
  fi
done

if [ "$rc" -eq 0 ]; then echo "lint: all groups ok"; fi
exit "$rc"
