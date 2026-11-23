# Public-repo files and rules

| File | Purpose |
|---|---|
| `LICENSE` | Apache-2.0 |
| `SECURITY.md` | reporting and the no-host/no-credential rule |
| `.github/CODEOWNERS` | `* @keskinege` |
| `.github/pull_request_template.md` | verification and rollback checklist |

## Rules

- No NIM address, hostname, endpoint or credential in a commit, artifact, manifest or log.
  `NIM_URL` is `https://manager-server`; `NIM_HOST` and `NIM_MGMT_ENDPOINT` are secrets.
- Backup artifacts store the endpoint as `nim-mgmt-endpoint.invalid`; `restore.sh` substitutes it.
- The repository is public. Treat a leaked value as public: rewrite history, delete artifacts,
  rotate the credential and open a GitHub Support purge request for cached commits and PR refs.
- PR validation currently uses the repository `NIM_*` secrets. Repository write access is
  NIM-admin equivalent until a scoped validator identity exists.
