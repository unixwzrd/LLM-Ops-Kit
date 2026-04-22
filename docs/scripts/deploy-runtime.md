# deploy-runtime

**Created**: 2026-04-17
**Updated**: 2026-04-17

`deploy-runtime` is the script-level staged deployment orchestrator for Phase 1.
Use repo-root `./build-stage` as the normal operator entrypoint.

```bash
./scripts/deploy-runtime [-c <name>] [-n|-d] [-y] [-v] [--dry-run] [--stage-dir <path>]
```

This helper is documented centrally in [DEPLOYMENT_SYNC_RUNBOOK](../DEPLOYMENT_SYNC_RUNBOOK.md).

Keep this page as the quick pointer only:

- `deploy-runtime` loads or creates `stage/deploy_config/<name>.env`
- stages the virtual target filesystem under `stage/<config-name>/`
- pushes the staged install and bin trees over SSH/rsync
- runs remote post-deploy validation

Use `--dry-run` to validate the plan and transport path without applying remote changes.
Use `-v` to show detailed staging and rsync activity.
