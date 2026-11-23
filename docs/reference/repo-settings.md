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
| `NIM_USER` | repository | `admin` |
| `NIM_PASSWORD` | repository | the local admin password |
| `NIM_MGMT_ENDPOINT` | repository | `mgmt usage_report` endpoint, substituted at render/publish |
| `NGINX_PLUS_JWT` | **not set** | required for the real Plus image; the F5 registry rejects the cluster JWT |

The `nim` environment exists and both publish jobs use it, but it has no protection rules yet.
PR validation reads the repository `NIM_*` secrets. NIM exposes only the local `admin` identity
(`CreateUser` has no password field and the htpasswd has one entry), so a scoped validator account
is a known follow-up. Until then, repository write access is NIM-admin equivalent.

## Public-repo files

- `LICENSE` — Apache-2.0
- `SECURITY.md` — reporting and the no-host/no-credential rule
- `.github/CODEOWNERS` — `* @keskinege`
- `.github/pull_request_template.md` — verification and rollback checklist

## Artifacts

Backups are redacted (`nim-mgmt-endpoint.invalid`) and kept for 7 days. Do not restore the old
90-day retention or write `NIM_URL` into a manifest.
