# plus-docker-nginx-config

Git source of truth for the `/etc/nginx` trees published to **several** NGINX Instance
Manager instance groups at once. One directory per group:

```
groups/
  docker-plus-cluster/          # NIM instance group of the same name
    group.yaml                  # name + policy for the linters
    nginx.conf                  # -> /etc/nginx/nginx.conf
    conf.d/site.conf            # -> /etc/nginx/conf.d/site.conf
  k8s-plus-cluster/
    group.yaml
    nginx.conf
    conf.d/plus-api.conf        # managed for this group (it owns the Plus API file)
    mime.types                  # managed for this group
scripts/
  lint.sh                invariants for every group
  nginx-test.sh          real `nginx -t` per group (OSS image, Plus bits neutralised)
  backup-config.sh       snapshot the group's CURRENT config from NIM
  publish.sh             publish one group tree
```

The directory name **is** the NIM instance group name. `group.yaml` carries the policy the
linters read (`require_mgmt: true` when the members must keep the `mgmt` usage-report block).

## Flow

| Event | What runs |
|---|---|
| Pull request touching `groups/`, `scripts/`, the workflow | `lint` → invariants + `nginx -t` **for every group**. Nothing is published. |
| Merge to `main` | `lint`, then only the groups whose directory changed are published, each with `externalId = github.sha` |
| `workflow_dispatch` | all groups are published |

Publishing a group: snapshot its current NIM config → `nim-group-config-backup-<group>-<run_id>`
artifact (90 days) → `POST` the tree → wait for the deployment → fail on any per-instance error.

## Adding a group

1. Create the group in NIM (or let it be created when the first member registers).
2. `mkdir groups/<nim-group-name>` and add `group.yaml`:

   ```yaml
   name: <nim-group-name>
   require_mgmt: true      # false for members that must not report usage
   ```

3. Add the tree the members run. **Include every file the group already owns** — a publish is
   declarative over the managed set, so a file you omit is deleted on the members.
4. Open a PR. Merging publishes only that group.

## Repository configuration

Variables: `NIM_URL` (`https://<nim-host>`).
Secrets: `NIM_USER`, `NIM_PASSWORD`.

The NIM is reached on its public IP because GitHub-hosted runners are not on the tailnet;
`nim-mgmt-endpoint.invalid` resolves to a `100.x` address they cannot route. TLS uses the internal
`manager-server` certificate, so the scripts call curl with `-k`.

`NIM_USER`/`NIM_PASSWORD` are the NIM admin credentials by design (this NIM exposes no scoped
service account). That makes **repo write access equivalent to NIM admin**: anyone who can edit
a workflow can read the secrets, so keep the repo private and its collaborator list tight.

## Run it locally

```bash
./scripts/lint.sh
./scripts/nginx-test.sh                                  # needs docker

GROUP=docker-plus-cluster \
NIM_URL=https://<nim-host> NIM_USER=… NIM_PASSWORD=… ./scripts/publish.sh
```

## Semantics you must know

- **Per-group managed set.** Each group's payload is declarative over its own tree. `k8s-plus-cluster`
  manages `nginx.conf`, `conf.d/plus-api.conf` and `mime.types`; `docker-plus-cluster` manages only
  `nginx.conf` and `conf.d/site.conf` (its Plus API file comes from the image and is left alone).
- **Only online members receive a publish.** A reconnecting instance is synced to the last
  successful group publish.
- **`status: successful` is not enough.** NIM reports success if *any* online member applied it;
  `publish.sh` fails on `details.failure`, on `details.error`, and when nothing applied.
- **A group with no members** accepts a publish and stores the config for future members; the job
  treats that as success and says so.
- **NIM dedupes by config hash.** Re-publishing an unchanged tree is a no-op that reports success.
- **The Plus `mgmt` block is main-context** and must stay where `require_mgmt` is true, or the
  instance drops out of NIM. `include /etc/nginx/conf.d/*.conf;` must always stay, or the Plus API
  disappears.
- **Never put a read-only mount or per-member divergence under `/etc/nginx`.** The agent rewrites the
  whole tree on apply, so per-instance TLS belongs outside it (see `/etc/nginx-tls` in
  `k8s-plus-cluster`, stubbed by the syntax test).
