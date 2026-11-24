# Rollback

## Template group (`template-cluster`)

There is no static tree for a template group. Roll back from the artifact captured before the bad
publish.

1. Download `nim-group-config-backup-template-cluster-<run_id>` from the workflow run you are
   backing out.
2. Unzip it into `backup/template-cluster/`.
3. Replay it:

   ```bash
   GROUP=template-cluster BACKUP_DIR=backup/template-cluster \
     NIM_MGMT_ENDPOINT=… NIM_URL=https://manager-server NIM_HOST=… \
     NIM_USER=… NIM_PASSWORD=… ./scripts/restore.sh
   ```

   `NIM_CA` defaults to `certs/nim-ca.pem`. The artifact stores the mgmt endpoint as
   `nim-mgmt-endpoint.invalid`; `restore.sh` substitutes the real value, which is why the artifact
   is safe to keep on a public repo.

4. Verify:

   ```bash
   GROUP=template-cluster NIM_URL=https://manager-server NIM_HOST=… \
     NIM_MGMT_ENDPOINT=… NIM_USER=… NIM_PASSWORD=… \
     ./scripts/check-live-drift.sh
   ```

   Expected `drift: none`, and each member passes `nginx -t`.

5. **Revert the bad commit in a PR.** `restore.sh` only changes what NIM holds; `main` still
   carries the bad change, so the next drift check reports it and the next push re-publishes it.
   Open `git revert <bad-sha>`, merge, and let `nginx-template.yml` publish the reverted render.
   Re-run `check-live-drift.sh` and confirm `drift: none` afterwards.

## Static group (`static-cluster`)

Restore the tree **on current `main`** and publish it. Do not check out the old commit: anything
before `#10` still uses `curl -k` and the old `NIM_URL` scheme, and the scripts have moved on.

```bash
# 1. Bring the last good tree back into the working branch, from the good commit
git restore --source=<good-sha> -- groups/static-cluster
git commit -m "rollback: restore static-cluster from <good-sha>"
# 2. Open a PR, merge it, and let nginx-static.yml publish (it lints and runs nginx -t first)
```

For an emergency publish without waiting for the merge, run the same tree through the current
scripts:

```bash
GROUP=static-cluster CONFIG_DIR=groups/static-cluster PRESERVE_AUX=1 \
  EXTERNAL_ID=<good-sha> NIM_MGMT_ENDPOINT=… NIM_URL=https://manager-server \
  NIM_HOST=… NIM_CA=certs/nim-ca.pem NIM_USER=… NIM_PASSWORD=… ./scripts/publish.sh
```

Then `./scripts/check-live-drift.sh` for `static-cluster`.

Either way the **commit** must be repaired too, or the next push re-publishes the bad tree.

## A group delete returns 412

An agent still names the group. Move it first (`agent-dynamic.conf`), restart `nginx-agent` in
place, then delete again.
