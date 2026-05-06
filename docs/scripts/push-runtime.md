# push-runtime

**Created**: 2026-04-17
**Updated**: 2026-04-27

Push a staged virtual target filesystem to the configured host list over SSH/rsync, then run remote post-deploy checks as the target user.

```bash
scripts/push-runtime [--config-name <name>] [--dry-run] [--skip-stage] [--stage-dir <path>] [--config-file <path>] [-v]
```

This is an internal helper command. Operators should use
`scripts/llmops-admin push` from the administrator workstation.

See [DEPLOYMENT_OVERVIEW](../DEPLOYMENT_OVERVIEW.md) for the supported
deployment model.

In short, `push-runtime`:

1. loads one local deployment config
2. builds the stage directory unless `--skip-stage` is used
3. syncs staged install and bin trees to each configured remote host
4. creates or validates the configured remote runtime venv
5. deploys managed links and verifies the runtime command surface
