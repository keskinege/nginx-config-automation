#!/usr/bin/env bash
# Validate every group tree with a real `nginx -t` using the OSS image.
#
# The trees are Plus-flavoured (`mgmt { ... }`), which OSS nginx rejects, so that
# block is stripped for this check only. Includes that point OUTSIDE /etc/nginx
# (per-instance TLS at /etc/nginx-tls, projected in from a Secret) are stubbed so
# syntax can be checked; their content is owned by the cluster, not this repo.
set -euo pipefail

cd "$(dirname "$0")/.."
IMAGE="${NGINX_TEST_IMAGE:-nginx:1.27-alpine}"
rc=0

for gdir in groups/*/; do
  g=$(basename "$gdir")
  echo "=== $g ==="
  if ! tar -cf - -C "$gdir" . | docker run --rm -i "$IMAGE" sh -euc '
    mkdir -p /src && tar -xf - -C /src
    rm -f /etc/nginx/conf.d/default.conf
    cp -a /src/. /etc/nginx/
    sed -i "/^mgmt[[:space:]]*{/,/^}/d" /etc/nginx/nginx.conf
    # Plus-only directives OSS nginx does not know. Commented for the syntax
    # check only; NIM runs its analyzer over the Plus-specific parts on publish.
    sed -i -E "s/^([[:space:]]*)(api[[:space:]].*)$/\\1# \\2/" /etc/nginx/conf.d/*.conf
    # Stub includes that live outside the managed tree.
    grep -rhoE "^[[:space:]]*include[[:space:]]+[^;*]+;" /etc/nginx 2>/dev/null \
      | sed -E "s/^[[:space:]]*include[[:space:]]+//; s/;$//" \
      | while read -r inc; do
          case "$inc" in
            /etc/nginx/*) ;;
            *) mkdir -p "$(dirname "$inc")"; [ -e "$inc" ] || : > "$inc"; echo "stubbed $inc";;
          esac
        done
    nginx -t
  '; then
    echo "::error::nginx -t failed for group $g"
    rc=1
  fi
done

exit "$rc"
