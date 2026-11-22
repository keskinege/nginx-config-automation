# nginx-config-automation

Git source of truth for the `/etc/nginx` configs published to NGINX Instance Manager instance
groups. A group is deployed in one of two modes:

| Mode | Source of truth | Publisher |
|---|---|---|
| `static` | `groups/<group>/*.conf` | `scripts/publish.sh` |
| `template` | `templates/` + `groups/<group>/inputs.yaml` | `scripts/render.sh` → `scripts/publish.sh` |

Currently both instance groups are template-managed. Their last static trees are retained in
`groups/` as the tested rollback source. The per-group `deploy_mode` in `group.yaml` decides
which workflow may publish it: exactly one.

## Layout

```
templates/
  base/nginx-base/
    meta.yaml                  # name, type, state, files (source -> target)
    base.tmpl                  # full config + augment injection points
    main.json http.json http-server.json http-upstream.json location.json stream.json
    README.md
    aux/etc/nginx/mime.types   # shipped as /etc/nginx/mime.types
  augments/
    site-docker/
      meta.yaml
      http.tmpl
      http.json
groups/
  docker-plus-cluster/         # template-managed
    group.yaml                 # name, require_mgmt, deploy_mode: template
    inputs.yaml                # baseData + augmentData
  k8s-plus-cluster/            # template-managed; static tree retained for rollback
    group.yaml                 # deploy_mode: template
    inputs.yaml
    nginx.conf
    conf.d/plus-api.conf       # rollback copy; removed on template publish
    mime.types
.nim/
  templates.lock.json          # template name -> uid
  rendered.lock.json           # group -> render sha256/crc32
scripts/
  lint.sh                      invariants + inputs for static groups
  lint-inputs.py               validate template names and /etc/nginx dirs
  nginx-test.sh                real `nginx -t` for static groups
  nginx-test-dir.sh            real `nginx -t` for one tree
  backup-config.sh             snapshot the group's CURRENT config from NIM
  render.sh                    compose a group from NIM templates + inputs
  sync_templates.py            create/update NIM templates from templates/
  check-live-drift.sh          compare live NIM config to the rendered hash
  tree_hash.py                 canonical SHA-256 / CRC32 of a config tree
  publish.sh                   publish a tree with externalId
  list-groups.sh               list groups by deploy_mode
```

## Flow

| Event | Static groups | Template groups |
|---|---|---|
| Pull request | `lint` + `nginx -t` | `lint-inputs` + `render` + hash check + `nginx -t` |
| Merge to `main` | only changed static groups publish | template changes re-render every template group; group changes publish that group |
| `workflow_dispatch` | all static groups | all template groups |

Both publish paths:

1. Snapshot the current NIM config to a 90-day artifact.
2. Build the payload.
3. `POST` it with `externalId = github.sha`.
4. Wait for the deployment.
5. Fail on `details.failure`, `details.error`, or when nothing applied.

## Adding or moving a group

1. Create the group in NIM (or let it be created when the first member registers).
2. `mkdir groups/<nim-group-name>` and add `group.yaml`:

   ```yaml
   name: <nim-group-name>
   require_mgmt: true      # false for members that must not report usage
   deploy_mode: static     # or template
   ```

3. **Static:** add the full tree. Include every file the group owns — a publish is declarative
   over the managed set, so a file you omit is deleted on the members.

   **Template:** add `inputs.yaml` and reference templates from `templates/`. See
   `groups/docker-plus-cluster/inputs.yaml` and `templates/base/nginx-base/`.

4. Open a PR. Merging publishes only the groups owned by the matching workflow.

A template edit must be applied to NIM manually (or by a future sync script) before merging;
otherwise `render.sh` composes the old NIM template and the hash does not change.

## Templates and inputs

`templates/base/nginx-base/base.tmpl` preserves the repo invariants:

- `mgmt { usage_report ... }` stays in main context when `require_mgmt` is true.
- `include /etc/nginx/conf.d/*.conf;` always stays.
- `include /etc/nginx-tls/server.conf;` is emitted only when `include_tls` is true.
- `mime.types` is shipped as an aux file at `/etc/nginx/mime.types`.

Augments are composed into `/etc/nginx/augments/http/<template-uid>.conf` and included from
`nginx.conf`. `site-docker` supplies the docker group's default server.

`groups/<group>/inputs.yaml` carries values, not file blobs:

```yaml
baseData:
  templateName: nginx-base
  main:
    templateInput:
      worker_connections: "2048"
      require_mgmt: true
      mgmt_endpoint: ovh-fr.tail7fa79.ts.net
      include_tls: false
  http:
    templateInput:
      access_log: /var/log/nginx/access.log
augmentData:
  - templateName: site-docker
    action: new
```

YAML inputs need `yq` (mikefarah v4); JSON inputs use only `python3`. Template names resolve
from `.nim/templates.lock.json` or from `GET /conf-templates`.

### Template sync

`scripts/sync_templates.py` creates missing templates and diffs files by name/content. It never
deletes a whole template; it can prune extra files inside a template.

```bash
# check local templates against NIM (2 = drift, no writes)
NIM_URL=… NIM_USER=… NIM_PASSWORD=… \
  python3 scripts/sync_templates.py --all --check

# apply
NIM_URL=… NIM_USER=… NIM_PASSWORD=… \
  python3 scripts/sync_templates.py --all

# one template, or preview
NIM_URL=… python3 scripts/sync_templates.py --template nginx-base
NIM_URL=… python3 scripts/sync_templates.py --all --dry-run
```

The template workflow runs `--check` before compose/publish, so a template change must be
applied to NIM before it can be merged and deployed. A weekly scheduled job runs
`scripts/check-live-drift.sh` for every template-mode group and fails if the live NIM config
differs from `.nim/rendered.lock.json`.

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest

./scripts/lint.sh
./scripts/nginx-test.sh                                  # static groups; needs docker
./scripts/nginx-test-dir.sh rendered/docker-plus-cluster # one tree

GROUP=docker-plus-cluster \
NIM_URL=https://<nim-host> NIM_USER=… NIM_PASSWORD=… ./scripts/publish.sh
```

### Render from templates

```bash
GROUP=docker-plus-cluster \
NIM_URL=https://<nim-host> NIM_USER=… NIM_PASSWORD=… \
OUT_DIR=rendered/docker-plus-cluster \
WRITE_HASH=1 HASH_FILE=.nim/rendered.lock.json \
./scripts/render.sh

# compose and print the file list, write nothing
DRY_RUN=1 GROUP=docker-plus-cluster … ./scripts/render.sh

# compare with the last recorded render (2 = changed, 3 = no record)
CHECK_HASH=1 GROUP=docker-plus-cluster … ./scripts/render.sh

# hash only
HASH_ONLY=1 GROUP=docker-plus-cluster … ./scripts/render.sh

# assert an exact hash
EXPECTED_SHA256=<sha256> GROUP=docker-plus-cluster … ./scripts/render.sh
```

Check the live NIM config against the recorded hash:

```bash
GROUP=docker-plus-cluster NIM_URL=… NIM_USER=… NIM_PASSWORD=… \
  ./scripts/check-live-drift.sh   # 0 no drift, 2 drift, 3 no recorded hash
```

`check-live-drift.sh` compares **configFiles only**; preserved aux files (such as
`/etc/nginx/tls/tls.crt`) are outside the Git-declarative set and are ignored.

`render.sh` hashes the **whole rendered tree** — every file recursively, including every
`conf.d/*.conf`, `augments/**`, and aux file. The recipe is `nginx-config-tree-v1`: sorted POSIX
paths, length-prefixed path and bytes. `render-manifest.txt` and lock files are excluded.
Generated `# __templateTag=...` comments are ignored (`--strip-template-tags`) because NIM may
name a different augment in that comment between otherwise identical composes; this keeps the
digest stable.

Hash any tree directly:

```bash
python3 scripts/tree_hash.py rendered/docker-plus-cluster
python3 scripts/tree_hash.py groups/docker-plus-cluster \
  --exclude group.yaml --exclude inputs.yaml
```

A hash change is a byte change, not a semantic one: comments and ordering count. Pair it with a
rendered diff and `nginx -t`.

## Publishing a rendered tree

`publish.sh` accepts `CONFIG_DIR` (default `groups/<group>`), `DRY_RUN=1`, and
`PRESERVE_AUX=1`. It excludes `group.yaml`, `inputs.yaml`, `render-manifest.txt`, dotfiles, and
`*.lock.json`.

`PRESERVE_AUX=1` carries the current group's `auxFiles` forward unchanged. This is how
`/etc/nginx/tls/tls.crt` survives the k8s cutover; aux files are outside the Git-declarative
set. Both workflows set it.

```bash
GROUP=docker-plus-cluster \
CONFIG_DIR=rendered/docker-plus-cluster \
PRESERVE_AUX=1 \
NIM_URL=… NIM_USER=… NIM_PASSWORD=… \
DRY_RUN=1 ./scripts/publish.sh
```

## Semantics you must know

- **Per-group managed set.** A publish is declarative over the group's tree; a file omitted from
  the payload is deleted on the members. After the migrations:
  - `docker-plus-cluster`: `nginx.conf`, `mime.types`, `augments/http/<site-docker>.conf`;
    the old `conf.d/site.conf` is removed.
  - `k8s-plus-cluster`: `nginx.conf`, `mime.types`, `augments/http/<site-k8s>.conf`,
    `augments/http/<plus-api>.conf`; the old `conf.d/plus-api.conf` is removed.
  - `/etc/nginx/tls/tls.crt` on k8s is preserved as an **aux** file with `PRESERVE_AUX=1`.
- **Static trees must be self-contained.** Every explicit `include /etc/nginx/<path>;` must
  exist in the tree. The retained static trees include `mime.types` for rollback; without it,
  rolling back after a template publish deletes the template-managed `mime.types` and
  `nginx -t` fails.
- **Only online members receive a publish.** A reconnecting instance is synced to the last
  successful group publish.
- **Offline members.** NIM stores the config but no member reports an outcome; `publish.sh`
  times out and exits `1`. The config applies when the members reconnect. Check
  `GET /systems/{systemUid}` → `.status.state` (`online`/`offline`) before treating a timeout as
  a bad config.
- **`status: successful` is not enough.** NIM reports success if *any* online member applied it;
  `publish.sh` fails on `details.failure`, `details.error`, and when nothing applied.
- **A group with no members** accepts a publish and stores the config for future members; the job
  treats that as success and says so.
- **NIM dedupes by config hash.** Re-publishing an unchanged tree is a no-op that reports success.
- **The Plus `mgmt` block is main-context** and must stay where `require_mgmt` is true, or the
  instance drops out of NIM. `include /etc/nginx/conf.d/*.conf;` must always stay, or the Plus API
  disappears.
- **Never put a read-only mount or per-member divergence under `/etc/nginx`.** The agent rewrites
  the whole tree on apply, so per-instance TLS belongs outside it (see `/etc/nginx-tls` in
  `k8s-plus-cluster`, stubbed by the syntax test).

## Repository configuration

Secrets: `NIM_URL`, `NIM_USER`, `NIM_PASSWORD`.

The NIM is reached on its public IP because GitHub-hosted runners are not on the tailnet;
`ovh-fr.tail7fa79.ts.net` resolves to a `100.x` address they cannot route. TLS uses the internal
`manager-server` certificate, so the scripts call curl with `-k`.

`NIM_USER`/`NIM_PASSWORD` are the NIM admin credentials by design (this NIM exposes no scoped
service account). That makes **repo write access equivalent to NIM admin**: anyone who can edit
a workflow can read the secrets, so keep the repo private and its collaborator list tight.
