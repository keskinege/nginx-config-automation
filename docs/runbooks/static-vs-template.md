# Static vs template: when and how

A group is in exactly one mode, set by `deploy_mode` in `groups/<group>/group.yaml`:

| Mode | Workflow | Source | Publisher |
|---|---|---|---|
| `static` | `nginx-config.yml` | `groups/<group>/*.conf` | `scripts/publish.sh` |
| `template` | `nginx-template.yml` | `templates/` + `groups/<group>/inputs.yaml` | `scripts/render.sh` → `publish.sh` |

`scripts/list-groups.sh static|template` is the source of truth for the CI matrix. Never let both
workflows publish one group: the mode gate is the only thing preventing last-writer-wins.

---

## 1. Decision guide

Use **static** when:

- the group is a one-off, a lab, or a small fixed set;
- the file layout is hand-authored and exact (`conf.d`, snippets, `mime.types`);
- files come from the image or a vendor and must not be templated;
- you need per-group divergence without a shared base;
- you want the simplest rollback (re-publish the tree);
- you do not want NIM template objects and submissions in the path.

Use **template** when:

- several groups share the same base structure;
- values differ (ports, server names, worker settings, include dirs);
- you want JSON-schema validation and a form-friendly input model;
- you want reusable augments (cache, OIDC, rate limiting, site blocks);
- configs are generated consistently and reviewed as inputs, not full trees;
- you accept the NIM template lifecycle (sync, snapshots, UID lock, compose).

Use **neither** for:

- image-provided files you do not intend to own;
- per-member values (TLS certs, hostnames) — keep them outside `/etc/nginx`
  (for example `/etc/nginx-tls/server.conf`).

### Trade-offs

| Concern | Static | Template |
|---|---|---|
| Duplication | High across groups | Low (shared base/augments) |
| Review unit | Full `nginx.conf`/`conf.d` diff | Template + input diff + rendered diff |
| Validation | `lint.sh` + `nginx -t` | `analyze` + compose + `nginx -t` |
| NIM objects | None | Templates, submissions, UID lock |
| Provenance | `externalId = git SHA` on publish | `externalId` on compose + publish |
| File layout | Exact | Composed; augments land under `/etc/nginx/augments/http/<uid>.conf` |
| Mode switch | Tree retained | Inputs/templates retained |
| Operational risk | Managed-set deletion; self-contained includes | Image-file duplication, snapshots, agent/UID churn |

Current examples:

- `static-cluster` — **static**; the classic tree is the only source.
- `template-cluster` — **template** (`nginx-base` + `site-k8s`; Plus API is image-provided).

---

## 2. Static model

1. `pull_request` → `nginx-config.yml` runs `pytest`, `lint.sh`, `nginx-test.sh`, `actionlint`.
2. `push` to `main` → changed static groups are detected with `scripts/list-groups.sh static`.
3. For each changed group: `backup-config.sh` → `publish.sh` with `CONFIG_DIR=groups/<group>`,
   `EXTERNAL_ID=github.sha`, `PRESERVE_AUX=1`.

Operational rules:

- The publish is declarative over `groups/<group>/`; a file omitted is deleted.
- Every explicit `include /etc/nginx/<path>;` must exist in the tree (`mime.types` included).
- `lint.sh` enforces `mgmt`, `include conf.d`, one `default_server`, tabs/whitespace, and explicit
  includes.
- `PRESERVE_AUX=1` carries current aux files forward (for example a certificate kept in NIM).
- Never put per-member divergence under `/etc/nginx`.

Useful commands:

```bash
./scripts/lint.sh
./scripts/nginx-test-dir.sh groups/<group>
GROUP=<group> CONFIG_DIR=groups/<group> PRESERVE_AUX=1 DRY_RUN=1 \
  NIM_URL=… NIM_USER=… NIM_PASSWORD=… NIM_MGMT_ENDPOINT=… ./scripts/publish.sh
GROUP=<group> CONFIG_DIR=groups/<group> PRESERVE_AUX=1 \
  EXTERNAL_ID="$(git rev-parse HEAD)" \
  NIM_URL=… NIM_USER=… NIM_PASSWORD=… NIM_MGMT_ENDPOINT=… ./scripts/publish.sh
```

---

## 3. Template model

1. Template source lives in `templates/base/...` and `templates/augments/...`; each has `meta.yaml`.
2. `sync_templates.py --check` verifies local templates match NIM; CI runs it.
3. `render.sh` composes `baseData` + `augmentData` from `groups/<group>/inputs.yaml` through NIM
   and writes `rendered/<group>/`.
4. `tree_hash.py` hashes the tree (`--strip-template-tags`); `.nim/rendered.lock.json` records it.
5. `publish.sh` publishes the rendered tree with the same declarative/`externalId` rules.
6. `nginx-template.yml` validates on PR, publishes on merge, and checks live drift weekly.

Operational rules:

- Template edits must be applied to NIM (`sync_templates.py`) before merging; CI's `--check` fails
  otherwise.
- Submissions pin a snapshot; use `useLatestFiles` or re-submit when changing templates.
- `PRESERVE_AUX=1` carries live aux files (for example `/etc/nginx/tls/tls.crt`) forward.
- `check-live-drift.sh` compares **configFiles** only; aux files are outside the Git-declarative
  set.
- NIM's `# __templateTag=...` comment names a random augment; hashes strip it.
- Image-provided servers (k8s `conf.d/plus-api.conf`) must not be duplicated by an augment.
- A Flux-managed member must have its agent restarted in place; do not `kubectl rollout restart`,
  which creates new NIM system IDs.

Useful commands:

```bash
NIM_URL=… NIM_USER=… NIM_PASSWORD=… python3 scripts/sync_templates.py --all --check
GROUP=<group> OUT_DIR=rendered/<group> WRITE_HASH=1 \
  HASH_FILE=.nim/rendered.lock.json \
  NIM_URL=… NIM_USER=… NIM_PASSWORD=… NIM_MGMT_ENDPOINT=… ./scripts/render.sh
./scripts/nginx-test-dir.sh rendered/<group>
GROUP=<group> CHECK_HASH=1 HASH_FILE=.nim/rendered.lock.json \
  NIM_URL=… NIM_USER=… NIM_PASSWORD=… ./scripts/render.sh
GROUP=<group> NIM_URL=… NIM_USER=… NIM_PASSWORD=… ./scripts/check-live-drift.sh
```

---

## 4. Switching static → template

1. Ensure the base/augment templates exist in NIM:

   ```bash
   NIM_URL=… NIM_USER=… NIM_PASSWORD=… python3 scripts/sync_templates.py --all --check
   ```

2. Add `groups/<group>/inputs.yaml` with `baseData`/`augmentData`.
3. Render and compare:

   ```bash
   GROUP=<group> OUT_DIR=rendered/<group> WRITE_HASH=1 \
     HASH_FILE=.nim/rendered.lock.json \
     NIM_URL=… NIM_USER=… NIM_PASSWORD=… ./scripts/render.sh
   ./scripts/nginx-test-dir.sh rendered/<group>
   diff -ru groups/<group> rendered/<group> \
     --exclude group.yaml --exclude inputs.yaml --exclude render-manifest.txt
   ```

4. Resolve every difference. Pay special attention to:
   - `mgmt {}` (main context);
   - `include /etc/nginx/conf.d/*.conf;`;
   - `include /etc/nginx-tls/server.conf;`;
   - image-provided files (`conf.d/plus-api.conf`, `mime.types`);
   - the augment file path (`/etc/nginx/augments/http/<uid>.conf`).
5. Set `deploy_mode: template` and commit `inputs.yaml` + `.nim/rendered.lock.json`.
6. Open a PR. The template workflow runs `sync_templates --check`, render, hash check, and
   `nginx -t`; on merge it publishes.
7. A template group has no static tree. Rollback is `scripts/restore.sh` from the backup artifact; see `rollback.md`.

---

## 5. Switching template → static

> `template-cluster` does not keep a static tree. Its rollback path is `rollback.md`; the procedure below applies only when you are deliberately converting a group that still has a tree.

1. Confirm the static tree is **self-contained**:
   - every explicit `include /etc/nginx/<path>;` exists;
   - `mime.types` is present if included;
   - no per-member files under `/etc/nginx`.
2. Validate:

   ```bash
   ./scripts/nginx-test-dir.sh groups/<group>
   ```

3. Preview the classic payload:

   ```bash
   GROUP=<group> CONFIG_DIR=groups/<group> PRESERVE_AUX=1 DRY_RUN=1 \
     NIM_URL=… NIM_USER=… NIM_PASSWORD=… ./scripts/publish.sh
   ```

4. Set `deploy_mode: static`.
5. Open a PR. `nginx-config.yml` runs `lint.sh` + `nginx-test.sh`; on merge the static workflow
   publishes the tree.
6. Verify the live config and members. The template augment file is deleted; the classic `conf.d`
   file is restored; aux files are preserved by `PRESERVE_AUX=1`.
7. If the switch is permanent, remove the template-only artifacts:
   - `groups/<group>/inputs.yaml`
   - the unused augment under `templates/augments/...`
   - its `.nim/templates.lock.json` entry
   - its `.nim/rendered.lock.json` entry
   - the NIM template object (only if `hasSubmissions` is `false`)

The docker restore is the reference implementation: static payload `nginx.conf`,
`conf.d/site.conf`, `mime.types`; template inputs and `site-docker` removed; the NIM template
deleted because it had no submissions.

---

## 6. Verification command set

```bash
./scripts/lint.sh
./scripts/nginx-test.sh                     # static groups
./scripts/nginx-test-dir.sh rendered/<g>    # template group
python3 scripts/sync_templates.py --all --check
GROUP=<g> NIM_URL=… ./scripts/check-live-drift.sh
./scripts/check-nim-agents.sh
./scripts/list-groups.sh static
./scripts/list-groups.sh template
```

Expected: each group under one mode; no lint/`nginx -t` failure; templates in sync; no live drift
for template groups; all NIM systems online.

---

## 7. Pitfalls learned the hard way

- **Static tree must be self-contained.** A classic rollback once deleted `mime.types` because a
  template publish had managed it; `nginx -t` failed. `lint.sh` now checks explicit `/etc/nginx`
  includes.
- **NIM's `__templateTag` comment is nondeterministic.** Raw hashes flap; use
  `tree_hash.py --strip-template-tags`.
- **Image-provided Plus API.** The k8s image already has `conf.d/plus-api.conf` on
  `127.0.0.1:9000`; adding a `plus-api` augment duplicates the server.
- **Aux files are not declarative.** Preserve certificates with `PRESERVE_AUX=1`;
  `check-live-drift` ignores them.
- **Pod restarts create new NIM system IDs.** Restart `nginx-agent` in place on Flux-managed
  members, then delete only offline stale systems.
- **One mode per group.** The `deploy_mode` gate prevents two workflows publishing the same group.
- **Template edits need `sync_templates.py`.** Merging a template change without syncing NIM leaves
  the workflow composing the old template.
- **Offline members look like a bad deploy.** NIM can report `successful` with empty `details`;
  check `GET /systems/{uid}` `.status.state` before rolling back.
- **The mgmt endpoint is a placeholder.** `base.tmpl` and the static `nginx.conf` ship
  `nim-mgmt-endpoint.invalid`; `render.sh` and `publish.sh` replace it from `NIM_MGMT_ENDPOINT` and
  exit with an error if it is unset. Set `mgmt_endpoint` in `inputs.yaml` only to pin a different
  value.
