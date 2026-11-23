# Script exit codes

| Script | Code | Meaning |
|---|---|---|
| `render.sh` | 0 | rendered (or verified) |
| | 1 | compose/API/inputs error |
| | 2 | `CHECK_HASH`/`EXPECTED_SHA256` mismatch |
| | 3 | no recorded hash for the group |
| | 4 | the tree still contains `nim-mgmt-endpoint.invalid` |
| `publish.sh` | 0 | applied (or stored for an empty group) |
| | 1 | rejected, no member applied, or a member failed |
| `backup-config.sh` | 0 | snapshot written |
| | 1 | group missing, or the endpoint is present and unset |
| `restore.sh` | 0 | backup replayed |
| | 1 | rejected or timed out |
| `check-live-drift.sh` | 0 | no drift |
| | 1 | group not found |
| | 2 | drift |
| | 3 | no recorded render hash |
| `check-nim-agents.sh` | 0 | all online |
| | 1 | NIM returned no systems |
| | 2 | one or more systems offline |
| `tree_hash.py` | 0 | hash printed |
| `sync_templates.py` | 0 | in sync / applied |
| | 1 | drift (with `--check`) or API error |
| `lint.sh` | 0 | all invariants hold |
| | 1 | an invariant failed |
| `group-mode.sh` | 2 | missing `group.yaml` or unknown `deploy_mode` |
| `detect-groups.sh` | 2 | bad mode or an unparsable group |
