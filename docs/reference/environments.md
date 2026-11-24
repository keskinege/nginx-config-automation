# Environments

## Connection model

Every script talks to NIM over HTTPS using a name the certificate is valid for:

- `NIM_URL=https://manager-server` — the certificate SAN; hostname verification needs this name.
- `NIM_HOST` — an address a GitHub-hosted runner can reach; curl uses
  `--resolve manager-server:443:$NIM_HOST`.
- `NIM_CA` — the internal CA, committed as `certs/nim-ca.pem`.
- CI maps the name in `/etc/hosts` for the Python client.

Never re-enable `curl -k`. `sync_templates.py` clears only Python's `VERIFY_X509_STRICT` flag
because the internal CA lacks the CA/B forum key-usage extension; chain and hostname checks stay
on.

## What the scripts assume

The production NIM, the instance groups and their members are described in the private
operations documentation, not here. This repository needs only the connection contract above.

The scripts assume:

- NIM exposes the `conf-templates` and instance-group APIs (see `prerequisites.md`);
- every group member runs NGINX Plus with the `mgmt` block and an NGINX Agent;
- a group is in exactly one mode, set by `deploy_mode` in `groups/<group>/group.yaml`;
- per-member TLS lives outside the managed tree; the trees include it from
  `/etc/nginx-tls/server.conf` and the syntax test stubs it.

Group names, member hostnames, deployment paths and credentials belong to the private
operations documentation.

## Container registry

`private-registry.nginx.com` authenticates with the **client certificate** `nginx-repo.crt`/`.key`,
not a JWT. CI installs it from `NGINX_REPO_CRT`/`NGINX_REPO_KEY`, restarts Docker, and pulls the
pinned Plus image. The runtime license is `NGINX_PLUS_JWT`.
