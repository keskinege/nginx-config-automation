# Adding a config file, site, or cluster

Task runbook for `nginx-config-automation`. For the pipeline view see
[../workflow.md](../workflow.md); for choosing a mode see
[static-vs-template.md](static-vs-template.md).

Pick the deploy mode first. The group's `deploy_mode` in `group.yaml` is the single gate that
decides which workflow may publish it.

| Situation | Mode |
|---|---|
| One group, hand-written tree, exact file layout | static |
| Several groups share a base, per-group values, schema validation | template |
| New `conf.d` file for a static group | static |
| New server block shared by many groups | template augment |
| File supplied by the image and you do not want to own it | neither — leave it alone |
| Per-member values (certificates, hostnames) | neither — keep outside `/etc/nginx` |

---

## 1. Add a static config file

1. Add the file under the group tree, for example `groups/<group>/conf.d/<name>.conf`.
   `nginx.conf` must include `include /etc/nginx/conf.d/*.conf;`, so a `conf.d/` file is picked up
   automatically.
2. If you add a new directory and an explicit include, the file must exist in the tree:

   ```nginx
   include /etc/nginx/snippets/<name>.conf;
   ```

   `scripts/lint.sh` rejects an explicit `/etc/nginx/<path>` include that is absent.
3. Validate:

   ```bash
   ./scripts/lint.sh
   ./scripts/nginx-test-dir.sh groups/<group>
   ```

4. Preview the exact publish payload:

   ```bash
   GROUP=<group> CONFIG_DIR=groups/<group> PRESERVE_AUX=1 DRY_RUN=1 \
     NIM_URL=… NIM_USER=… NIM_PASSWORD=… ./scripts/publish.sh
   ```

5. Open a PR. On merge the static workflow publishes the changed group.

**Managed-set rule:** the publish is declarative over `groups/<group>/`. Every file the group owns
must be present; a file you omit is deleted on the members. Do not add an image-supplied file to the
tree unless you intend to own it.

---

## 2. Add a static site/server block

1. Create `groups/<group>/conf.d/<site>.conf`:

   ```nginx
   server {
       listen 80 default_server;
       server_name example.com;

       location / {
           return 200 "ok\n";
           add_header Content-Type text/plain;
       }

       location = /healthz {
           access_log off;
           return 200 "ok";
       }
   }
   ```

2. Rules enforced by `scripts/lint.sh`:
   - exactly one `listen 80 default_server` per group tree;
   - `include /etc/nginx/conf.d/*.conf;` stays;
   - the `mgmt { ... }` block stays when `require_mgmt: true`;
   - no tabs or trailing whitespace;
   - explicit `/etc/nginx` includes must exist in the tree.

3. Validate and publish as in §1.

**TLS:** a certificate must not be a per-member file under `/etc/nginx`. Keep the 443 server and
cert in `/etc/nginx-tls/server.conf` (projected from a Secret) and include that file from
`nginx.conf`. The syntax test stubs it.

---

## 3. Add a template site/server block

1. Create the augment:

   ```text
   templates/augments/site-<name>/
     meta.yaml
     http.tmpl
     http.json
   ```

   `meta.yaml`:

   ```yaml
   name: site-<name>
   type: augment
   state: draft
   description: <site> server block.
   files:
     - source: http.tmpl
     - source: http.json
   ```

   `http.tmpl` is injected at the base template's `http` point:

   ```gotemplate
   server {
       listen 80;
       server_name <name>.example.com;
       location / {
           return 200 "ok\n";
       }
   }
   ```

2. Push the template to NIM:

   ```bash
   NIM_URL=… NIM_USER=… NIM_PASSWORD=… \
     python3 scripts/sync_templates.py --template site-<name>
   ```

   `--check` reports drift without writing; `--dry-run` previews.

3. Reference it from the group's `inputs.yaml`:

   ```yaml
   augmentData:
     - templateName: site-<name>
       action: new
   ```

4. Render, validate, and inspect:

   ```bash
   GROUP=<group> OUT_DIR=rendered/<group> WRITE_HASH=1 \
     HASH_FILE=.nim/rendered.lock.json \
     NIM_URL=… NIM_USER=… NIM_PASSWORD=… ./scripts/render.sh

   ./scripts/nginx-test-dir.sh rendered/<group>
   diff -ru groups/<group> rendered/<group> \
     --exclude group.yaml --exclude inputs.yaml --exclude render-manifest.txt
   ```

5. Open a PR. On merge the template workflow re-renders and publishes.

**Do not duplicate an image-provided server.** The k8s image already ships
`conf.d/plus-api.conf` on `127.0.0.1:9000`; adding a `plus-api` augment produces a conflicting
server warning. Check the running container before adding a server the image may already provide.

---

## 4. Add a template file or aux file

- **Templated block:** create the matching `*.tmpl` (`main`, `http`, `http-server`,
  `http-upstream`, `location`, `stream`, `stream-server`, `stream-upstream`) and list it in
  `meta.yaml`.
- **Static extra file:** put it under the template's `aux/` tree and map it in `meta.yaml`:

  ```yaml
  files:
    - source: aux/etc/nginx/snippets/proxy.conf
      target: /etc/nginx/snippets/proxy.conf
  ```

  Aux content is not templated. `render.sh` materializes it in `rendered/<group>/` and the normal
  publish manages it as a file.
- **Out-of-Git aux (certificates):** do **not** add it to a template. Keep it in NIM and publish
  with `PRESERVE_AUX=1`; both workflows already set it. `check-live-drift.sh` ignores aux files.

Sync and validate as in §3.

---

## 5. Add a new cluster/group

### 5.1 Create the NIM group first

The group `name` is immutable after creation; `displayName` can change later.

```bash
BASE="${NIM_URL%/}/api/platform/v1"
curl -sk -u "$NIM_USER:$NIM_PASSWORD" -X POST "$BASE/instance-groups" \
  -H 'Content-Type: application/json' \
  -d '{"name":"<group>","displayName":"<Group> (static|template)"}'
```

The repo directory name **must equal** the NIM group name; the scripts use the basename to find the
group.

### 5.2 Add the repo entry

```bash
mkdir groups/<group>
cat > groups/<group>/group.yaml <<'YAML'
name: <group>
require_mgmt: true          # false only if members must not report usage
deploy_mode: static         # or template
YAML
```

### 5.3 Static group

Add the full managed tree:

```text
groups/<group>/
  nginx.conf
  conf.d/<site>.conf
  mime.types
```

Include `mime.types` if `nginx.conf` has `include /etc/nginx/mime.types;`. The tree must be
self-contained. Then validate and dry-run as in §1.

### 5.4 Template group

Add `groups/<group>/inputs.yaml`:

```yaml
baseData:
  templateName: nginx-base
  main:
    templateInput:
      worker_connections: "1024"
      require_mgmt: true
      mgmt_endpoint: <instance-manager-endpoint>
      include_tls: false
  http:
    templateInput:
      access_log: /var/log/nginx/access.log
augmentData: []
```

`mgmt_endpoint` is the NIM address the members report to; it must be reachable from the members,
not from GitHub runners. Ensure the referenced templates exist in NIM
(`sync_templates.py --check`), then render and test as in §3.

### 5.5 Members and first publish

Members join by naming the group in `agent-dynamic.conf` (`instance_group: <group>`) and restarting
`nginx-agent`. A group with zero members accepts a publish and stores it for future members. Back up
the current config before the first publish:

```bash
GROUP=<group> OUT_DIR=backup/<group>-pre-publish EXTERNAL_ID=manual EXTERNAL_ID_TYPE=other \
  NIM_URL=… NIM_USER=… NIM_PASSWORD=… ./scripts/backup-config.sh
```

`scripts/list-groups.sh` and both workflows discover the new directory automatically; no workflow
edit is needed.

---

## 6. Verification checklist

```bash
./scripts/lint.sh
./scripts/nginx-test.sh                     # static groups
./scripts/nginx-test-dir.sh rendered/<g>    # template group
python3 scripts/sync_templates.py --all --check
GROUP=<g> CHECK_HASH=1 HASH_FILE=.nim/rendered.lock.json ./scripts/render.sh   # template
GROUP=<g> ./scripts/check-live-drift.sh     # template
./scripts/check-nim-agents.sh
./scripts/list-groups.sh static
./scripts/list-groups.sh template
```

Expected: the group appears under exactly one mode; lint and `nginx -t` pass; templates are in
sync; live drift is `none`; every NIM system is online.
