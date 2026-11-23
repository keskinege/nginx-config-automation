# Script options

## `render.sh`

| Variable | Meaning |
|---|---|
| `GROUP` | group directory name (required) |
| `NIM_URL`, `NIM_USER`, `NIM_PASSWORD` | NIM credentials (required) |
| `NIM_HOST`, `NIM_CA` | `--resolve` target and CA path |
| `NIM_MGMT_ENDPOINT` | substituted for `nim-mgmt-endpoint.invalid` |
| `MGMT_PLACEHOLDER` | override the placeholder text |
| `INPUTS` | inputs file (default `groups/$GROUP/inputs.yaml`) |
| `OUT_DIR` | output tree (default `rendered/$GROUP`) |
| `MODE` | `compose` (default) or `submissions` |
| `DRY_RUN=1` | compose, print the list and hash, write nothing |
| `HASH_ONLY=1` | print the hash, write nothing |
| `CHECK_HASH=1` | compare to `HASH_FILE`; also writes the tree on success |
| `WRITE_HASH=1` | record the hash in `HASH_FILE` |
| `EXPECTED_SHA256` | fail unless the canonical hash matches |
| `HASH_FILE` | default `.nim/rendered.lock.json` |
| `WRITE_LOCK=1` | merge template name → uid into `.nim/templates.lock.json` |

## `publish.sh`

`GROUP`, `CONFIG_DIR`, `ROOT_DIR`, `DRY_RUN`, `PRESERVE_AUX`, `EXTERNAL_ID`,
`EXTERNAL_ID_TYPE`, `NIM_MGMT_ENDPOINT`, `MGMT_PLACEHOLDER`.

## `backup-config.sh`

`GROUP`, `OUT_DIR`, `EXTERNAL_ID`, `EXTERNAL_ID_TYPE`, `NIM_MGMT_ENDPOINT`.

## `restore.sh`

`GROUP`, `BACKUP_DIR`, `EXTERNAL_ID`, `NIM_MGMT_ENDPOINT`, `NIM_URL`, `NIM_USER`,
`NIM_PASSWORD`, `NIM_HOST`, `NIM_CA`.

## `check-live-drift.sh`

`GROUP`, `HASH_FILE`, `NIM_MGMT_ENDPOINT`, `NIM_URL`, `NIM_USER`, `NIM_PASSWORD`,
`NIM_HOST`, `NIM_CA`.

## `check-nim-agents.sh`

`VERBOSE=1` prints each hostname; the default prints state counts.

## `sync_templates.py`

`--all`, `--template NAME`, `--check`, `--dry-run`, `--no-prune`.

## Discovery

`list-groups.sh [static|template]`, `detect-groups.sh MODE BEFORE SHA EVENT`,
`group-mode.sh GROUPS_DIR/GROUP`.
