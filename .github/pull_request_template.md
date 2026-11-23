## What changed

## Which groups are affected

<!-- static-cluster / template-cluster / none -->

## Verification

- [ ] `pytest`
- [ ] `./scripts/lint.sh`
- [ ] `actionlint`
- [ ] `nginx -t` for every affected tree
- [ ] template groups: `CHECK_HASH=1` render matches `.nim/rendered.lock.json`
- [ ] no NIM host, endpoint or credential in the diff

## Risk and rollback

<!-- restore.sh <backup-artifact> for template groups; re-publish the static tree otherwise -->
