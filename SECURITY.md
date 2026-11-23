# Security policy

## Reporting

Do not open a public issue for a vulnerability. Use GitHub's private vulnerability reporting on
this repository, or contact the maintainer listed in `CODEOWNERS`.

## What this repository assumes

- The NGINX Instance Manager (NIM) API is reachable from GitHub-hosted runners. It is protected
  by TLS verification against the pinned `certs/nim-ca.pem` and by an admin credential stored in
  GitHub secrets.
- The repository is public. No NIM address, hostname, endpoint or credential belongs in a commit,
  an artifact, a manifest or a log. Report any that you find as a vulnerability.
- Published NIM configs are declarative. A group's managed set is exactly the files in
  `groups/<group>/`, or the files rendered from `templates/` plus `groups/<group>/inputs.yaml`.
- PR validation currently uses the repository `NIM_*` secrets because NIM exposes only the local
  `admin` identity. A scoped validator account is a known follow-up; treat repository write access
  as NIM admin equivalent until it exists.
