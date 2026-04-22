# setup-deploy

**Created**: 2026-04-17
**Updated**: 2026-04-17

Create or update one local-only deployment config file used by staged SSH rollout.

```bash
scripts/setup-deploy [--config-name <name>] [--reset] [--config-file <path>] [--print-template]
```

This helper is usually invoked by `deploy-runtime`.
The full staged deploy workflow is documented in [DEPLOYMENT_SYNC_RUNBOOK](../DEPLOYMENT_SYNC_RUNBOOK.md).

This command:

- writes one named config file under `stage/deploy_config/`
- keeps the config file on the admin machine only
- supports `--reset` to re-prompt an existing config using saved values as defaults
- supports `--print-template` for manual editing workflows
