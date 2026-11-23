# Environments

## Production NIM

The production NGINX Instance Manager is a **Docker Compose** deployment on `ovh-fr`, not the
`nim` namespace in the k3s cluster.

| Item | Value |
|---|---|
| Compose directory | `/home/debian/nim` |
| Container | `f5c7fef825a8_nim-nim-1` (`private-registry.nginx.com/nms/nim-standalone-compose:2.23.1`) |
| Public listener | `0.0.0.0:443` (docker-proxy) |
| Local auth | `/data/local-auth/.htpasswd` in the `nim_nim-data` volume (`admin`, `apr1`) |
| Bootstrap secret | `/home/debian/nim/admin_password.txt` → `/run/secrets/nim_admin_password` |

The k3s `nim` namespace is a **separate** instance. Do not change it when working on production.

## TLS

The served leaf is `CN=manager-server`, issued by `CN=apigw-svc`, with SAN
`DNS:manager-server, DNS:nim.local, IP:127.0.0.1`. The public root is committed as
`certs/nim-ca.pem`.

- `NIM_URL=https://manager-server` (the SAN; hostname verification needs this name)
- `NIM_HOST` is the address a runner can reach; curl uses
  `--resolve manager-server:443:$NIM_HOST`
- CI maps the name in `/etc/hosts` for the Python client
- `NIM_CA` defaults to `certs/nim-ca.pem`

Never re-enable `curl -k`. `sync_templates.py` clears only Python's `VERIFY_X509_STRICT` flag
because the internal CA lacks the CA/B forum key-usage extension; chain and hostname checks stay
on.

## Instance groups and members

| Group | Mode | Members |
|---|---|---|
| `static-cluster` | static | `plus-docker-1`, `plus-docker-2` (KubeVirt VMs, agent in the `nginx-plus` container) |
| `template-cluster` | template | `plus-k8s-1`, `plus-k8s-2` (k3s pods, Flux-managed) |

- The Docker VMs mount `/var/lib/nginx-plus/agent` into the container at `/var/lib/nginx-agent`.
- The k8s agent state lives on a PVC at `/var/lib/nginx-agent`; the init container seeds it with
  `cp -n`, so a ConfigMap edit does not reach a running pod.
- `plus-k8s` is Flux-managed from `k3s-gh/apps/nginx-standalone/plus-k8s`. Restart `nginx-agent` in
  place; a pod recreation registers a new system ID.
- Per-member TLS lives outside the managed tree: `/etc/nginx-tls/server.conf` on k8s, projected
  from a Secret.
