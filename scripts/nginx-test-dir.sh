#!/usr/bin/env bash
# Real `nginx -t` for one config tree using the NGINX Plus image.
#
# Requires NGINX_PLUS_JWT (the runtime license) and the F5 registry client
# certificate in /etc/docker/certs.d/private-registry.nginx.com
# (client.cert + client.key). CI installs both from secrets.
set -euo pipefail

DIR="${1:?usage: nginx-test-dir.sh DIR}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Reject includes that only pass because the stub would create them.
"$SCRIPT_DIR/check-includes.sh" "$DIR"
IMAGE="${NGINX_TEST_IMAGE:-private-registry.nginx.com/nginx-plus/agent:nginx-plus-20261118@sha256:7ba2bd0045205be0c9e81601da4d0f8b36105de880b914903029e33e8485e436}"
: "${NGINX_PLUS_JWT:?set NGINX_PLUS_JWT (NGINX Plus license JWT)}"

tar -cf - -C "$DIR" . | docker run --rm -i --entrypoint sh \
  -e "NGINX_LICENSE_JWT=${NGINX_PLUS_JWT}" \
  "$IMAGE" -euc '
    mkdir -p /src && tar -xf - -C /src
    rm -f /etc/nginx/conf.d/default.conf
    cp -a /src/. /etc/nginx/
    printf "%s" "$NGINX_LICENSE_JWT" > /etc/nginx/license.jwt
    grep -rhoE "^[[:space:]]*include[[:space:]]+[^;*]+;" /etc/nginx 2>/dev/null \
      | sed -E "s/^[[:space:]]*include[[:space:]]+//; s/;$//" \
      | while read -r inc; do
          case "$inc" in
            /etc/nginx/*) ;;
            *) mkdir -p "$(dirname "$inc")"; [ -e "$inc" ] || : > "$inc"; echo "stubbed $inc";;
          esac
        done
    nginx -t'
