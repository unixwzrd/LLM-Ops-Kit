# llmops-admin

**Created**: 2026-04-27
**Updated**: 2026-04-27

Back: [Script Guides](./README.md)

Administrator workstation deployment command.

```bash
scripts/llmops-admin inventory-validate
scripts/llmops-admin bootstrap-host [--role <role>] [--tag <tag>] [--host-name <name>] [--dry-run]
scripts/llmops-admin stage [--bundle-id <id>] [--role <role>] [--tag <tag>] [--dry-run]
scripts/llmops-admin push [--stage <path>] [--workers <n>] [--dry-run]
scripts/llmops-admin apply [--stage <path>] [--workers <n>] [--restart <script>] [--dry-run]
scripts/llmops-admin config-settings [--host-name <name>] [--model <profile>]
scripts/llmops-admin config-doctor [--role <role>] [--model <profile>]
```

Use this command from the administrator workstation to:

- validate host inventory
- bootstrap SSH access
- build local deployment bundles
- push packages and host config in parallel
- apply a pushed bundle on remote hosts
- install or refresh deployed runtime scripts and command links
- inspect rendered config and source layers

Start with [Deployment Overview](../DEPLOYMENT_OVERVIEW.md) for the full
operator workflow.

The target hosts can be cloud instances, local servers, virtual machines, or
hybrid nodes. The inventory decides where the bundle goes; the admin workstation
does the staging and fan-out.
