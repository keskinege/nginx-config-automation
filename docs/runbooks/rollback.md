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

## Static group (`static-cluster`)

Re-publish the tree from the last good commit:

```bash
git switch --detach <good-sha>
GROUP=static-cluster CONFIG_DIR=groups/static-cluster PRESERVE_AUX=1 \
  EXTERNAL_ID=<good-sha> NIM_MGMT_ENDPOINT=… NIM_URL=https://manager-server \
  NIM_HOST=… NIM_USER=… NIM_PASSWORD=… ./scripts/publish.sh
```

Then re-run `check-live-drift.sh` for `static-cluster`.

## A group delete returns 412

An agent still names the group. Move it first (`agent-dynamic.conf`), restart `nginx-agent` in
place, then delete again.
