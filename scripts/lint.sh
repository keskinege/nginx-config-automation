#!/usr/bin/env bash
# Lint every group tree under groups/<group>/ for the invariants NIM and the
# Plus image depend on. A group is a directory whose name is the NIM instance
# group name, carrying a group.yaml with its metadata.
set -euo pipefail

cd "$(dirname "$0")/.."
rc=0
shopt -s nullglob

for gdir in groups/*/; do
  g=$(basename "$gdir")

  if [ ! -f "$gdir/nginx.conf" ]; then
    echo "::error file=$gdir::missing nginx.conf"
    rc=1
    continue
  fi

  declared=$(sed -n 's/^name:[[:space:]]*//p' "$gdir/group.yaml" 2>/dev/null | head -1)
  if [ "$declared" != "$g" ]; then
    echo "::error file=$gdir/group.yaml::name '$declared' does not match directory '$g'"
    rc=1
  fi

  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    echo "::error::tab character: $hit"
    rc=1
  done < <(grep -rn $'\t' "$gdir" || true)

  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    echo "::error::trailing whitespace: $hit"
    rc=1
  done < <(grep -rnE ' +$' "$gdir" || true)

  if ! grep -qE '^[[:space:]]*include[[:space:]]+/etc/nginx/conf\.d/\*\.conf;' "$gdir/nginx.conf"; then
    echo "::error file=$gdir/nginx.conf::must include /etc/nginx/conf.d/*.conf"
    rc=1
  fi

  require_mgmt=$(sed -n 's/^require_mgmt:[[:space:]]*//p' "$gdir/group.yaml" 2>/dev/null | head -1)
  if [ "$require_mgmt" = "true" ] && ! grep -qE '^mgmt[[:space:]]*\{' "$gdir/nginx.conf"; then
    echo "::error file=$gdir/nginx.conf::must keep the mgmt { usage_report ... } block (main context)"
    rc=1
  fi

  servers=$(grep -rnE 'listen[[:space:]]+80\b' "$gdir" | wc -l | tr -d ' ')
  defaults=$(grep -rnE 'listen[[:space:]]+80[[:space:]]+default_server' "$gdir" | wc -l | tr -d ' ')
  if [ "$servers" -gt 0 ] && [ "$defaults" -eq 0 ]; then
    echo "::error file=$gdir::a :80 server exists but none is default_server"
    rc=1
  fi
  if [ "$defaults" -gt 1 ]; then
    echo "::error file=$gdir::more than one 'listen 80 default_server' in the tree"
    rc=1
  fi

  echo "lint: $g ok" || true
done

if [ "$rc" -eq 0 ]; then echo "lint: all groups ok"; fi
exit "$rc"
