# setup-deploy

**Created**: 2026-04-17
**Updated**: 2026-04-27

Create or update one local-only deployment config file used by staged SSH rollout.

```bash
scripts/setup-deploy [--config-name <name>] [--reset] [--config-file <path>] [--print-template]
```

This is an internal helper retained for deployment implementation details.

Operators should use `scripts/llmops-admin` from the administrator workstation.
For the supported deployment workflow, start with
[DEPLOYMENT_OVERVIEW](../DEPLOYMENT_OVERVIEW.md).

This command:

- writes one named config file under `stage/deploy_config/`
- keeps the config file on the admin machine only
- supports `--reset` to re-prompt an existing config using saved values as defaults
- supports `--print-template` for manual editing workflows
