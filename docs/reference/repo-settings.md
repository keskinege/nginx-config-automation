# Repository settings

## Branch protection (`main`)

- Required status check: **`ci-gate`** only (strict: branch must be up to date)
- Pull request required; admins are enforced
- Force pushes and deletions disabled

`ci-gate` is an always-run aggregate in `ci.yml`. A docs-only PR creates no static or template
job, but `ci-gate` still reports.

## Secrets

| Secret | Scope | Purpose |
|---|---|---|
| `NIM_URL` | repository | `https://manager-server` (the certificate SAN) |
| `NIM_HOST` | repository | address a GitHub runner can reach; used by `--resolve` and `/etc/hosts` |
| `NIM_USER` / `NIM_PASSWORD` | **`nim` environment** (`main` only) | the local `admin` credential; publish jobs only |
| `NIM_VALIDATOR_USER` / `NIM_VALIDATOR_PASSWORD` | repository | `ci-validator`: templates/groups read + compose; no publish or user management |
| `NIM_MGMT_ENDPOINT` | repository | `mgmt usage_report` endpoint, substituted at render/publish |
| `NGINX_REPO_CRT` | repository | F5 registry client certificate (`nginx-repo.crt`) |
| `NGINX_REPO_KEY` | repository | F5 registry client key (`nginx-repo.key`) |
| `NGINX_PLUS_JWT` | repository | runtime NGINX Plus license for `nginx -t` |

The `nim` environment allows deployment only from `main`; it holds the admin credential for the
publish and drift jobs. PR validation uses `ci-validator`, a separate htpasswd entry plus a NIM role
limited to `TEMPLATES: READ`, `TEMPLATE-SUBMISSIONS: READ` and `INSTANCE-GROUPS: READ`. It can
compose but cannot publish, delete a group, or manage users.

## Public-repo files

- `LICENSE` — Apache-2.0
- `SECURITY.md` — reporting and the no-host/no-credential rule
- `.github/CODEOWNERS` — `* @keskinege`
- `.github/pull_request_template.md` — verification and rollback checklist

## Artifacts

Backups are redacted (`nim-mgmt-endpoint.invalid`) and kept for 7 days. Do not restore the old
90-day retention or write `NIM_URL` into a manifest.
