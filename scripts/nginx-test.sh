#!/usr/bin/env bash
# Validate every static group tree with a real `nginx -t` using the OSS image.
# Template-mode groups are validated from the rendered tree in their own workflow.
set -euo pipefail

cd "$(dirname "$0")/.."
rc=0

for gdir in groups/*/; do
  g=$(basename "$gdir")
  mode=$(yq -r '.deploy_mode // "static"' "$gdir/group.yaml" 2>/dev/null || echo static)
  if [ "$mode" = template ]; then
    echo "=== $g (template; skipped) ==="
    continue
  fi

  echo "=== $g ==="
  if ! ./scripts/nginx-test-dir.sh "$gdir"; then
    echo "::error::nginx -t failed for group $g"
    rc=1
  fi
done

exit "$rc"
