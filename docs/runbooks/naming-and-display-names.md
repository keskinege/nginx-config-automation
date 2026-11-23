# Group and workflow naming

Three different names are involved. Do not confuse "make the mode visible" with "rename the NIM
group".

| Thing | Mutable? | Current |
|---|---|---|
| NIM instance-group `name` | **No** (immutable after create) | `docker-plus-cluster`, `k8s-plus-cluster` |
| NIM instance-group `displayName` | Yes (`PATCH`) | same as `name` |
| GitHub workflow display name | Yes (file + `name:`) | `nginx-config`, `nginx-template` |
| GitHub workflow file | Yes | `.github/workflows/nginx-config.yml`, `nginx-template.yml` |

---

## 1. Recommended: change display names, not NIM group names

Keep `name` stable (`docker-plus-cluster`, `k8s-plus-cluster`) and set a human-friendly
`displayName` that includes the mode:

- `Docker Plus — static`
- `K8s Plus — template`

API:

```bash
BASE="${NIM_URL%/}/api/platform/v1"
AUTH=(-sk -u "$NIM_USER:$NIM_PASSWORD")

# Look up the uid by name first
curl "${AUTH[@]}" "$BASE/instance-groups" \
  | jq -r '.items[] | select(.name=="docker-plus-cluster") | .uid'

curl "${AUTH[@]}" -X PATCH "$BASE/instance-groups/<group-uid>" \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Docker Plus — static"}'
```

`PATCH /instance-groups/{uid}` accepts `displayName`, `description`, and `baseConfigName`; it does
**not** accept `name`.

### Repo directory names

The scripts assume the directory basename equals the NIM group `name` (`publish.sh`,
`backup-config.sh`, `list-groups.sh`, and therefore `matrix.group`). Do not rename
`groups/docker-plus-cluster` to `groups/static-cluster` unless you do the full migration in §3. Add
a `# static` / `# template` comment or rely on `deploy_mode`.

---

## 2. Workflow names

Current:

| File | Workflow `name:` | Mode |
|---|---|---|
| `.github/workflows/nginx-config.yml` | `nginx-config` | static |
| `.github/workflows/nginx-template.yml` | `nginx-template` | template |

Recommended:

| File | Workflow `name:` | Why |
|---|---|---|
| `.github/workflows/nginx-static.yml` | `nginx-static` | symmetric with `nginx-template`; drops the legacy "config" |
| `.github/workflows/nginx-template.yml` | `nginx-template` | already clear |

Also make the publish job names distinct so the checks list does not show two identical
`publish <group>` entries:

- static: `name: publish static ${{ matrix.group }}`
- template: `name: publish template ${{ matrix.group }}`

**Keep the `lint + nginx -t` job name.** Branch protection on `main` requires that exact status
context:

```text
required_status_checks: ["lint + nginx -t"]
```

Renaming the workflow `name:` or the file does not change the check context. Renaming the `lint`
job would require updating branch protection at the same time.

### Safe rename procedure

1. `git mv .github/workflows/nginx-config.yml .github/workflows/nginx-static.yml`
2. Change `name: nginx-config` to `name: nginx-static`.
3. Optionally change `name: publish ${{ matrix.group }}` to
   `name: publish static ${{ matrix.group }}`.
4. Update README/docs references to `nginx-static.yml`.
5. Run `actionlint`.
6. PR: the required `lint + nginx -t` check still runs and passes (the workflow triggers on
   `.github/workflows/**`).
7. Merge. The old workflow disappears from the active list; historical runs stay under the old
   name. The rename itself has no deploy side effect.

The template workflow can take the same publish-job rename in the same PR. Do not rename
`validate template groups` or `check live drift` unless you update the docs that reference them.

---

## 3. Actual NIM group rename (only if the identifier must change)

Example target: `docker-plus-cluster` → `static-cluster`, `k8s-plus-cluster` → `template-cluster`.

NIM has **no rename operation** for an instance group. A rename is a migration:

1. Create the new group:

   ```bash
   curl -sk -u "$NIM_USER:$NIM_PASSWORD" -X POST "$BASE/instance-groups" \
     -H 'Content-Type: application/json' \
     -d '{"name":"static-cluster","displayName":"Docker Plus — static"}'
   ```

2. Move every member:
   - **Agent-managed hosts:** set `instance_group: <new-name>` in `agent-dynamic.conf`, then restart
     `nginx-agent`.
   - **Flux-managed members:** update the `agent-dynamic.conf` key in the member's ConfigMap and the
     Flux source, then let Flux reconcile or restart the agent in place. Do not use
     `kubectl rollout restart` (new NIM system IDs).
3. Publish to the new group:

   ```bash
   GROUP=<new-name> CONFIG_DIR=groups/<old-dir> \
     EXTERNAL_ID=manual EXTERNAL_ID_TYPE=other PRESERVE_AUX=1 \
     NIM_URL=… NIM_USER=… NIM_PASSWORD=… ./scripts/publish.sh
   ```

4. Verify both members applied and the old group is empty.
5. Delete the old group:

   ```bash
   curl -sk -u "$NIM_USER:$NIM_PASSWORD" -X DELETE "$BASE/instance-groups/<old-uid>"
   ```

   NIM returns `412` while agents still name the old group.
6. Rename the repo directory and `group.yaml name` to the new NIM name; update `inputs.yaml`, docs,
   and backup references.
7. `externalId`/config history starts fresh on the new group; the old history is on the deleted
   group.

Risks: members are briefly unmanaged during the move; a Flux change must be coordinated; the VM
change is per-host; NIM group history is lost; automation and docs must be updated atomically. This
is not a cosmetic rename.

**Recommendation:** keep the NIM `name` stable and express the mode through `displayName` and
`deploy_mode`. Rename the **workflows** to `nginx-static` / `nginx-template` if symmetry matters;
that is safe and reversible.

---

## 4. Checklist

```bash
# group names should match directory names
for d in groups/*/; do
  g=$(basename "$d")
  n=$(yq -r '.name' "$d/group.yaml")
  [ "$g" = "$n" ] && echo "ok $g" || echo "MISMATCH $g != $n"
done

# workflow names/files
ls .github/workflows/
grep -n '^name:' .github/workflows/*.yml

# mode discovery
./scripts/list-groups.sh static
./scripts/list-groups.sh template

# branch protection still expects this exact job name
gh api repos/<owner>/<repo>/branches/main/protection \
  --jq '.required_status_checks.contexts'
```
