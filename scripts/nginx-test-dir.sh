#!/usr/bin/env bash
# Real `nginx -t` for one config tree using the OSS image.
#
# The trees are Plus-flavoured (`mgmt { ... }`, `api`), which OSS nginx rejects,
# so those blocks are neutralised for this check only. Includes that point
# OUTSIDE /etc/nginx (per-instance TLS at /etc/nginx-tls, projected in from a
# Secret) are stubbed so syntax can be checked; their content is owned by the
# cluster, not this repo.
set -euo pipefail

DIR="${1:?usage: nginx-test-dir.sh DIR}"
IMAGE="${NGINX_TEST_IMAGE:-nginx:1.27-alpine}"

tar -cf - -C "$DIR" . | docker run --rm -i "$IMAGE" sh -euc '
  mkdir -p /src && tar -xf - -C /src
  rm -f /etc/nginx/conf.d/default.conf
  cp -a /src/. /etc/nginx/
  sed -i "/^mgmt[[:space:]]*{/,/^}/d" /etc/nginx/nginx.conf
  # Plus-only directives OSS nginx does not know. Commented for the syntax
  # check only; NIM runs its analyzer over the Plus-specific parts on publish.
  sed -i -E "s/^([[:space:]]*)(api[[:space:]].*)$/\\1# \\2/" /etc/nginx/nginx.conf /etc/nginx/conf.d/*.conf /etc/nginx/augments/http/*.conf 2>/dev/null || true
  # Stub includes that live outside the managed tree.
  grep -rhoE "^[[:space:]]*include[[:space:]]+[^;*]+;" /etc/nginx 2>/dev/null \
    | sed -E "s/^[[:space:]]*include[[:space:]]+//; s/;$//" \
    | while read -r inc; do
        case "$inc" in
          /etc/nginx/*) ;;
          *) mkdir -p "$(dirname "$inc")"; [ -e "$inc" ] || : > "$inc"; echo "stubbed $inc";;
        esac
      done
  nginx -t'
