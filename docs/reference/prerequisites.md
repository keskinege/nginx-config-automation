# Prerequisites and versions

What a workstation or runner needs before the scripts will work.

| Tool | Version | Why |
|---|---|---|
| Python | 3.12 (CI), 3.x local | `render.sh`, `sync_templates.py`, tests |
| mikefarah `yq` | **v4.54.3** | `group-mode.sh`, `lint.sh`, `sync_templates.py` |
| `jq` | any v1.6+ | payload and manifest handling |
| `curl` | any with `--cacert` | all NIM calls |
| Docker | any recent | `nginx -t` in the pinned OSS image |
| NIM | 2.23.1+ (this deployment) | `conf-templates` and instance-group APIs |
| NGINX Plus | R33+ | the `mgmt { usage_report ... }` block |
| NGINX Agent | 2.x | membership in `agent-dynamic.conf` |

The important trap: **do not use the Python `yq` package**. It is a different tool with different
flags and breaks `group-mode.sh`, `lint.sh` and `sync_templates.py`. Install mikefarah's Go binary:

```bash
yq --version     # must print: yq (https://github.com/mikefarah/yq/) version v4.54.3
```

CI installs it through `.github/actions/setup-yq`, which pins v4.54.3 and checks its SHA-256.

Install the Python test dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

`nginx -t` uses the real Plus image
`private-registry.nginx.com/nginx-plus/agent:nginx-plus-20261118@sha256:7ba2bd…`. Two credentials
are required:

- the F5 registry **client certificate** (`nginx-repo.crt`/`.key`, stored as `NGINX_REPO_CRT` and
  `NGINX_REPO_KEY`) in `/etc/docker/certs.d/private-registry.nginx.com`; this is not a JWT;
- a valid runtime **license** (`NGINX_PLUS_JWT`). The `license.jwt` in the old `nginx-repo` export
  expired in 2026; CI uses the current lab subscription license (`NGINX_PLUS_JWT`).
