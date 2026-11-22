# nginx-base

Base template for the `nginx-config-automation` groups.

It preserves the repo invariants:

- `mgmt { usage_report ... }` stays in main context when `require_mgmt` is true.
- `include /etc/nginx/conf.d/*.conf;` always stays.
- `include /etc/nginx-tls/server.conf;` is emitted only when `include_tls` is true.
- `mime.types` is shipped as an aux file at `/etc/nginx/mime.types`.

Inputs live under `main.templateInput`; group-specific server blocks come from augments at the
`http` injection point.
