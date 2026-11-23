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

`nginx -t` uses `nginx:1.27-alpine@sha256:65645c…` by default. The real NGINX Plus image is a
follow-up: the F5 registry does not accept the cluster license JWT, so CI keeps the OSS image and
neutralises Plus-only directives.
