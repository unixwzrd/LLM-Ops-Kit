# deploy-runtime

**Created**: 2026-04-17
**Updated**: 2026-04-27

`deploy-runtime` is an internal helper retained for the deployment
implementation.

Operators should use `scripts/llmops-admin` from the administrator workstation.

```bash
./scripts/deploy-runtime [-c <name>] [-n|-d] [-y] [-v] [--dry-run] [--stage-dir <path>]
```

For the supported deployment model, start with
[DEPLOYMENT_OVERVIEW](../DEPLOYMENT_OVERVIEW.md).

This page is a maintainer note only:

- `deploy-runtime` loads or creates `stage/deploy_config/<name>.env`
- stages the virtual target filesystem under `stage/<config-name>/`
- pushes the staged install and bin trees over SSH/rsync
- runs remote post-deploy validation

Use `--dry-run` to validate the plan and transport path without applying remote changes.
Use `-v` to show detailed staging and rsync activity.
