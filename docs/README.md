# Documentation

Repository-local docs for `nginx-config-automation`. Start with the workflow page if you are new
to the repo; the runbooks are task-oriented.

| Document | Use it when |
|---|---|
| [workflow.md](workflow.md) | You need the whole picture: diagrams, triggers, job names, and the step-by-step static and template paths. |
| [runbooks/adding-configs-sites-and-clusters.md](runbooks/adding-configs-sites-and-clusters.md) | You are adding a config file, a site/server block, a template augment, or a whole cluster. |
| [runbooks/static-vs-template.md](runbooks/static-vs-template.md) | You need to choose a mode, or switch a group between static and template. |
| [runbooks/naming-and-display-names.md](runbooks/naming-and-display-names.md) | You are changing group, display, or workflow names — and need to know what is immutable. |
| [runbooks/rollback.md](runbooks/rollback.md) | A publish went wrong: restore a template group from a backup, or re-publish a static tree. |
| [reference/prerequisites.md](reference/prerequisites.md) | Tool versions, the mikefarah-vs-Python `yq` trap, and the Plus-image status. |
| [reference/environments.md](reference/environments.md) | Where the production NIM runs, the CA and names, the groups and their members. |
| [reference/repo-settings.md](reference/repo-settings.md) | `ci-gate`, secrets, the `nim` environment, and the public-repo files. |
| [reference/exit-codes.md](reference/exit-codes.md) | What each script's exit code means. |
| [reference/options.md](reference/options.md) | Every environment variable and flag. |
| [reference/public-files.md](reference/public-files.md) | License, security policy, owners, and the no-host rule. |
| [runbooks/lock-regeneration.md](runbooks/lock-regeneration.md) | Update `.nim/rendered.lock.json` after a template or input change. |
| [runbooks/decommission.md](runbooks/decommission.md) | Retire a group without stranding members. |
| [runbooks/troubleshooting.md](runbooks/troubleshooting.md) | Offline members, publish timeouts, drift, 412, TLS and registry errors. |

## The 60-second version

1. A group lives in `groups/<group>/` with `group.yaml` setting `deploy_mode: static|template`.
2. `static` groups publish their tree directly; `template` groups are composed from `templates/`
   plus `groups/<group>/inputs.yaml`.
3. A pull request only validates. A push to `main` publishes the changed groups with
   `externalId = <commit SHA>`.
4. `static-cluster` is static; `template-cluster` is template.

> The directory name **is** the NIM instance-group name, and that name is immutable. Use
> `deploy_mode` and `displayName` to express the mode, not the group name.

## Conventions in these docs

- Commands use `NIM_URL=… NIM_USER=… NIM_PASSWORD=…`; never commit a NIM host or credential.
- Any command that renders or publishes also needs `NIM_MGMT_ENDPOINT`, which replaces the
  `nim-mgmt-endpoint.invalid` placeholder in the `mgmt` block.
- `<group>` and `<g>` are placeholders for a group directory name.
- `…` in a command is a value you supply, not literal shell.
