#!/usr/bin/env bash
# Lint the config tree for the invariants that NIM / the Plus image depend on.
# Fails on: tabs, trailing whitespace, missing registration blocks, a :80 server
# without exactly one default_server.
set -euo pipefail

cd "$(dirname "$0")/.."
rc=0

if grep -rn $'\t' config/ ; then
  echo "::error::tab characters in config/ (use spaces)"
  rc=1
fi

if grep -rnE ' +$' config/ ; then
  echo "::error::trailing whitespace in config/"
  rc=1
fi

if ! grep -qE '^[[:space:]]*include[[:space:]]+/etc/nginx/conf\.d/\*\.conf;' config/nginx.conf; then
  echo "::error::config/nginx.conf must include /etc/nginx/conf.d/*.conf (the Plus API lives there)"
  rc=1
fi

if ! grep -qE '^mgmt[[:space:]]*\{' config/nginx.conf; then
  echo "::error::config/nginx.conf must keep the mgmt { usage_report ... } block (main context)"
  rc=1
fi

servers=$(grep -rnE 'listen[[:space:]]+80\b' config/ | wc -l | tr -d ' ')
defaults=$(grep -rnE 'listen[[:space:]]+80[[:space:]]+default_server' config/ | wc -l | tr -d ' ')
if [ "$servers" -gt 0 ] && [ "$defaults" -eq 0 ]; then
  echo "::error::a :80 server exists but none is default_server"
  rc=1
fi
if [ "$defaults" -gt 1 ]; then
  echo "::error::more than one 'listen 80 default_server' in the tree"
  rc=1
fi

if [ "$rc" -eq 0 ]; then echo "lint: ok"; fi
exit "$rc"
