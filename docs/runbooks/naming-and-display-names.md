# Group and workflow naming

Three different names are involved. Do not confuse "make the mode visible" with "rename the NIM
group".

| Thing | Mutable? | Current |
|---|---|---|
| NIM instance-group `name` | **No** (immutable after create) | `static-cluster`, `template-cluster` |
| NIM instance-group `displayName` | Yes (`PATCH`) | `Docker Plus — static`, `K8s Plus — template` |
| GitHub workflow display name | Yes (file + `name:`) | `nginx-static`, `nginx-template` |
| GitHub workflow file | Yes | `.github/workflows/nginx-static.yml`, `nginx-template.yml` |

---

## 1. Keep the group name stable; label with `displayName`

The groups are now `static-cluster` (static) and `template-cluster` (template). Those names are the
permanent identifiers: the agent, the scripts, CI, and the `externalId` history all use them. Do
not rename them again without doing the migration in §3.

Set a human-friendly `displayName` for the UI; it can change at any time:

- `Docker Plus — static`
- `K8s Plus — template`

API:

```bash
BASE="${NIM_URL%/}/api/platform/v1"
AUTH=(--cacert certs/nim-ca.pem --resolve "manager-server:443:$NIM_HOST" -u "$NIM_USER:$NIM_PASSWORD")

# Look up the uid by name first
curl "${AUTH[@]}" "$BASE/instance-groups" \
  | jq -r '.items[] | select(.name=="static-cluster") | .uid'

curl "${AUTH[@]}" -X PATCH "$BASE/instance-groups/<group-uid>" \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Docker Plus — static"}'
```

`PATCH /instance-groups/{uid}` accepts `displayName`, `description`, and `baseConfigName`; it does
**not** accept `name`.

### Repo directory names

The scripts assume the directory basename equals the NIM group `name` (`publish.sh`,
`backup-config.sh`, `list-groups.sh`, and therefore `matrix.group`). Rename the directory and the
NIM group together, or not at all. If you need a different identifier, do the full migration in §3.

---

## 2. Workflow names

Current:

| File | Workflow `name:` | Mode |
|---|---|---|
| `.github/workflows/ci.yml` | `ci` | PR gate (`ci-gate`) |
| `.github/workflows/nginx-static.yml` | `nginx-static` | static deploy |
| `.github/workflows/nginx-template.yml` | `nginx-template` | template |

Recommended:

| File | Workflow `name:` | Why |
|---|---|---|
| `.github/workflows/nginx-static.yml` | `nginx-static` | symmetric with `nginx-template`; drops the legacy "config" |
| `.github/workflows/nginx-template.yml` | `nginx-template` | already clear |

Both workflows name the job `publish ${{ matrix.group }}`; the workflow name (`nginx-static`,
`nginx-template`) keeps the checks list unambiguous.

**The required check is `ci-gate`.** It is the aggregate gate in `ci.yml`; branch protection on
`main` requires exactly that context:

```text
required_status_checks: ["ci-gate"]
```

Renaming the workflow `name:` or the file does not change the check context. Renaming the `lint`
job would require updating branch protection at the same time.

### Safe rename procedure

The rename is already applied: the file is `nginx-static.yml`, `name: nginx-static`, and the
publish job is `publish ${{ matrix.group }}` (the workflow name distinguishes them). Keep the required context `ci-gate` in
`ci.yml`; do not rename it without updating branch protection in the same change.

The `template` job is named `template validation`. Do not rename `ci-gate` without updating
branch protection in the same change.

---

## 3. Renaming a NIM group (migration)

NIM has **no rename operation** for an instance group. This is the procedure used to move
`docker-plus-cluster` → `static-cluster` and `k8s-plus-cluster` → `template-cluster`. Use the same
steps for any future rename:

1. Create the new group:

   ```bash
   curl --cacert certs/nim-ca.pem --resolve "manager-server:443:$NIM_HOST" -u "$NIM_USER:$NIM_PASSWORD" -X POST "$BASE/instance-groups" \
     -H 'Content-Type: application/json' \
     -d '{"name":"<new-name>","displayName":"<New Name>"}'
   ```

2. Move every member:
   - **Agent-managed hosts:** set `instance_group: <new-name>` in `agent-dynamic.conf`, then restart
     `nginx-agent`.
   - **Kubernetes members:** edit `/var/lib/nginx-agent/agent-dynamic.conf` on the persisted agent
     state volume, not only the ConfigMap. The init container seeds that file with `cp -n`, so a
     ConfigMap change never reaches a running pod. Update the ConfigMap/Flux source as well for
     future pods, then restart `nginx-agent` in place. Do not recreate the pod (new system ID).
3. Publish to the new group:

   ```bash
   GROUP=<new-name> CONFIG_DIR=groups/<old-dir> \
     EXTERNAL_ID=manual EXTERNAL_ID_TYPE=other PRESERVE_AUX=1 \
     NIM_URL=… NIM_USER=… NIM_PASSWORD=… ./scripts/publish.sh
   ```

4. Verify both members applied and the old group is empty.
5. Delete the old group:

   ```bash
   curl --cacert certs/nim-ca.pem --resolve "manager-server:443:$NIM_HOST" -u "$NIM_USER:$NIM_PASSWORD" -X DELETE "$BASE/instance-groups/<old-uid>"
   ```

   NIM returns `412` while agents still name the old group.
6. Rename the repo directory and `group.yaml name` to the new NIM name; update `inputs.yaml`, docs,
   and backup references.
7. `externalId`/config history starts fresh on the new group; the old history is on the deleted
   group.

Risks: members are briefly unmanaged during the move; a Flux change must be coordinated; the VM
change is per-host; NIM group history is lost; automation and docs must be updated atomically. This
is not a cosmetic rename.

**Recommendation:** the current names already encode the mode; keep them. Use `displayName` for
labels. The workflows are already `nginx-static` / `nginx-template`; keep them.

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
