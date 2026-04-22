# push-runtime

**Created**: 2026-04-17
**Updated**: 2026-04-17

Push a staged virtual target filesystem to the configured host list over SSH/rsync, then run remote post-deploy checks as the target user.

```bash
scripts/push-runtime [--config-name <name>] [--dry-run] [--skip-stage] [--stage-dir <path>] [--config-file <path>] [-v]
```

This is an internal helper command. Operators should normally use `./build-stage`.
See [DEPLOYMENT_SYNC_RUNBOOK](../DEPLOYMENT_SYNC_RUNBOOK.md) for the full deploy flow.

In short, `push-runtime`:

1. loads one local deployment config
2. builds the stage directory unless `--skip-stage` is used
3. syncs staged install and bin trees to each configured remote host
4. creates or validates the configured remote runtime venv
5. deploys managed links and verifies the runtime command surface
