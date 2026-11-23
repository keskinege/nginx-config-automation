# Troubleshooting

## A member is offline

```bash
./scripts/check-nim-agents.sh
```

Restart the **agent process in place**; do not recreate the pod. The k8s agent is started by
`start.sh` as a child of nginx:

```bash
kill <pid>; sleep 1; nohup nginx-agent >>/var/log/nginx-agent/agent.log 2>&1 &
```

A pod recreation registers a new NIM system ID and leaves a stale member. Delete only stale
offline records.

## Publish timed out with no outcome

NIM can store the config and return `successful` with empty `details` when the members are
offline. Check `GET /systems/{uid}` `.status.state`; do not roll back solely because of the
timeout. The config applies on reconnect.

## Drift

```bash
GROUP=static-cluster   … ./scripts/check-live-drift.sh
GROUP=template-cluster … ./scripts/check-live-drift.sh   # needs NIM_MGMT_ENDPOINT
```

`2` is drift, `3` is a missing lock. For a template group, roll back with `restore.sh`; for a
static group, re-publish the previous commit's tree.

## A group delete returns 412

An agent still names the group. Move it first, restart the agent in place, then delete again.

## `nginx -t` fails on an include

The tree is not self-contained. Add the included file (for `static-cluster`, `mime.types`) or
remove the include. `lint.sh` catches explicit `/etc/nginx` includes that are absent.

## Python: `CA cert does not include key usage extension`

The internal `apigw-svc` CA predates the CA/B forum extensions. `sync_templates.py` clears only
`VERIFY_X509_STRICT`; do not disable verification. curl is unaffected.

## F5 registry returns 400 for the Plus image

The cluster license JWT is not accepted as a registry credential. CI keeps the pinned OSS image;
supply a MyF5 registry JWT as `NGINX_PLUS_JWT` to enable the real Plus image.
