#!/usr/bin/env bash
# Validate the tree with a real `nginx -t` using the OSS image.
#
# The tree is Plus-flavoured (`mgmt { ... }`), which OSS nginx rejects, so the
# block is stripped for this check only. Everything else — includes, server
# blocks, syntax — is validated exactly as published. NIM runs its own analyzer
# on publish, which is what finally validates the Plus-specific parts.
#
# The tree is streamed in as a tar rather than bind-mounted, so this works on
# macOS/Docker Desktop (where /tmp is not a shared path) as well as on runners.
set -euo pipefail

cd "$(dirname "$0")/.."
IMAGE="${NGINX_TEST_IMAGE:-nginx:1.27-alpine}"

tar -cf - -C config . | docker run --rm -i "$IMAGE" sh -euc '
  mkdir -p /src && tar -xf - -C /src
  # The image ships conf.d/default.conf on :80; this repo owns the :80 server.
  rm -f /etc/nginx/conf.d/default.conf
  cp -a /src/. /etc/nginx/
  # Plus-only block, not understood by OSS nginx.
  sed -i "/^mgmt[[:space:]]*{/,/^}/d" /etc/nginx/nginx.conf
  echo "--- included files ---"
  nginx -T 2>&1 | grep -E "^# configuration file" || true
  echo "--- nginx -t ---"
  nginx -t
'
