# plus-docker-nginx-config

Git source of truth for the **`/etc/nginx` tree** published to the OVH-FR NGINX
Instance Manager instance group `docker-plus-cluster` (the two `plus-docker` KubeVirt VMs
running NGINX Plus in Docker).

```
config/            ->  /etc/nginx/** inside each managed instance
config/nginx.conf      http{} with the conf.d include + the Plus `mgmt` block
config/conf.d/         site servers (the Plus API listener comes from the image)
scripts/lint.sh        invariants: tabs, whitespace, mgmt, conf.d include, one :80 default
scripts/nginx-test.sh  real `nginx -t` in nginx:1.27-alpine (Plus block stripped)
scripts/publish.sh     POST the tree to the instance group, poll the deployment
```

## Flow

| Event | What runs |
|---|---|
| Pull request touching `config/`, `scripts/`, the workflow | `lint` → invariants + `nginx -t`. **Nothing is published.** |
| Merge / push to `main` | `lint`, then `publish`: the tree is sent to the group with `externalId = github.sha`, and the job fails unless every online member applied it |
| Manual (`workflow_dispatch`) | same as a push |

`externalId` is the commit SHA, so NIM shows which revision each instance runs
(`GET /api/platform/v1/instance-groups/{uid}` → `configVersion`).

## Repository configuration

Variables (Settings → Variables):

| Name | Value |
|---|---|
| `NIM_URL` | `https://<nim-host>` |
| `NIM_INSTANCE_GROUP` | `docker-plus-cluster` |

Secrets (Settings → Secrets):

| Name | Meaning |
|---|---|
| `NIM_USER` | NIM API user |
| `NIM_PASSWORD` | NIM API password |

The NIM is reached on its public IP because GitHub-hosted runners are not on the tailnet;
`ovh-fr.tail7fa79.ts.net` resolves to a `100.x` address they cannot route. TLS uses the
internal `manager-server` certificate, so the scripts call curl with `-k`.
**Rotate `NIM_PASSWORD` to a dedicated service account before using this outside the lab.**

## Run it locally

```bash
./scripts/lint.sh
./scripts/nginx-test.sh                       # needs docker

NIM_URL=https://<nim-host> NIM_GROUP=docker-plus-cluster \
NIM_USER=… NIM_PASSWORD=… ./scripts/publish.sh
```

## Semantics you must know

- **The payload is declarative for the files NIM manages.** Every file under `config/` is
  published under `/etc/nginx/`; a file removed from this repo is **deleted** on the
  instances at the next publish. Files that ship inside the image (notably
  `conf.d/plus-api.conf`, which serves the Plus API on `127.0.0.1:9000`) are not managed and
  are left alone — do not add a file here that shadows one of them unless you intend to own it.
- **Only online members receive a publish.** A reconnecting instance is synced to the last
  successful group publish.
- **`status: successful` is not enough.** NIM reports success if *any* online member applied
  the config; `scripts/publish.sh` fails on any entry in `details.failure`, on
  `details.error`, and when nothing applied at all.
- **NIM dedupes by config hash.** Re-running a workflow whose tree is byte-identical to the
  last successful publish is a no-op that reports success. Any real change (or a different
  `config/`) produces a new hash.
- `mgmt { usage_report endpoint=ovh-fr.tail7fa79.ts.net; }` is **main-context** and must stay,
  or the instances drop out of NIM; the `include /etc/nginx/conf.d/*.conf;` line must stay, or
  the Plus API disappears.
- An instance that is recreated (new container, fresh VM) re-seeds from Git on the VM and
  then catches up with the last group publish on reconnect.
