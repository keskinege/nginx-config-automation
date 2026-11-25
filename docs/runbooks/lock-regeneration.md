# Regenerating the render lock

`.nim/rendered.lock.json` stores the canonical hash of the **placeholder** tree, before the mgmt
endpoint is substituted. It is therefore independent of `NIM_MGMT_ENDPOINT` and does not need a
credential to update.

When you change a template, `inputs.yaml`, or `templates.lock.json`:

```bash
GROUP=template-cluster OUT_DIR=rendered/template-cluster WRITE_HASH=1 \
  HASH_FILE=.nim/rendered.lock.json NIM_MGMT_ENDPOINT=… \
  NIM_URL=https://manager-server NIM_HOST=… NIM_USER=… NIM_PASSWORD=… \
  ./scripts/render.sh
```

Commit the lock in the same PR as the change. CI runs `CHECK_HASH=1`, which verifies and writes
the tree; a mismatch fails the gate.

The hash replaces each template UID with its template name before hashing, so it does not matter
whether you rendered against the real templates or a `pr-<n>-` namespace: regenerate the lock
with `TEMPLATE_PREFIX=…` if that is the only namespace your account can see. Any stale lock is
caught in the PR, not at deploy.

The manifest records both `render_sha256` (the lock) and `published_sha256` (the substituted
tree). Drift normalizes the live endpoint back to the placeholder before hashing, so the lock
does not change when the secret changes.
