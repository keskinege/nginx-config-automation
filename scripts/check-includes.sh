#!/usr/bin/env bash
# Reject includes that point outside the managed tree.
#
#   ./scripts/check-includes.sh rendered/template-cluster
#
# `nginx-test-dir.sh` stubs includes that are satisfied by the image or by a
# per-member mount. Stubbing anything else turns a typo (`/etc/ngnix/x.conf`)
# into an empty file, so the tree passes `nginx -t` and fails on the instance.
# Only the paths in ALLOWED_INCLUDE_STUBS may be stubbed.
set -euo pipefail

DIR="${1:?usage: check-includes.sh DIR}"
ALLOWED="${ALLOWED_INCLUDE_STUBS:-/etc/nginx-tls/server.conf}"
[ -d "$DIR" ] || { echo "::error::no such tree: $DIR" >&2; exit 1; }

rc=0
while IFS= read -r inc; do
  [ -n "$inc" ] || continue
  case "$inc" in
    /etc/nginx/*) continue ;;
    /*) ;;                 # absolute outside /etc/nginx: needs an allowlist entry
    *) continue ;;         # relative include resolves under the prefix
  esac
  allowed=0
  read -r -a stubs <<<"$ALLOWED"
  for stub in "${stubs[@]}"; do
    [ "$inc" = "$stub" ] && allowed=1
  done
  if [ "$allowed" -eq 0 ]; then
    echo "::error::include $inc is outside /etc/nginx and is not an allowed stub ($ALLOWED)" >&2
    rc=1
  fi
done < <(grep -rhoE '^[[:space:]]*include[[:space:]]+[^;*]+;' "$DIR" 2>/dev/null \
  | sed -E 's/^[[:space:]]*include[[:space:]]+//; s/;$//')

exit "$rc"
