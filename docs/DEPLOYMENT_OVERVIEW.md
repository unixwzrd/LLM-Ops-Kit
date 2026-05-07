# Deployment Overview

**Created**: 2026-04-27
**Updated**: 2026-05-07

Back: [Documentation Index](./INDEX.md)

## Purpose

This document is the operator-level map for deploying `LLM-Ops-Kit`.

The deployment model is an administrator workstation flow:

1. maintain host inventory and deployment config locally
2. bootstrap SSH access to each target host once
3. build a local staged package
4. push package and host config to selected hosts in parallel
5. apply the staged package on each remote host
6. install or refresh the runtime command links on each host

## Deployment Entry Point

Use `llmops-admin` for deployment work:

```bash
scripts/llmops-admin inventory-validate
scripts/llmops-admin bootstrap-host --role llm --dry-run
scripts/llmops-admin deploy-plan --dry-run --bundle-id smoke
scripts/llmops-admin stage --dry-run --bundle-id smoke
scripts/llmops-admin push --dry-run --workers 4
scripts/llmops-admin apply --dry-run --workers 4
```

Lower-level scripts may exist in the repo because `llmops-admin` uses them for
packaging, linking, and verification. They are implementation details, not a
separate operator deployment flow.

## Inventory

The admin workflow is inventory driven. The preferred live inventory path is:

```text
~/.config/llm-ops/inventory.json
```

If that file is missing, `llmops-admin` falls back to the legacy admin
inventory and then the checked-in example:

```text
~/.llm-ops/inventory.yml
deploy/inventory.yml
```

The docs copy lives at:

```text
docs/inventory.example.yml
```

Each host record must define:

- `name`: stable inventory name
- `role`: one of `admin`, `llm`, `agent`, or `hybrid`
- `host`: DNS name or IP address
- `user`: SSH user
- `port`: SSH port
- `install_root`: remote install root, normally `~/.llm-ops`
- `config_profile`: layered config profile name
- `ssh_key`: local private key path
- `tags`: optional selectors such as `production`, `model`, or `agent`

Validate inventory before staging or pushing:

```bash
scripts/llmops-admin inventory-validate
scripts/llmops-admin inventory-validate --role llm
scripts/llmops-admin inventory-validate --tag production
scripts/llmops-admin inventory-validate --host-name llm-primary
```

## SSH Bootstrap

SSH setup is explicit and separate from package deployment. For each selected
host, `bootstrap-host` plans or performs:

- deploy key creation when the configured key is missing
- public key installation with `ssh-copy-id`
- noninteractive SSH verification
- remote runtime directory creation
- `.llmops-ready` marker creation under the remote install root

Dry run first:

```bash
scripts/llmops-admin bootstrap-host --role llm --dry-run
```

Then bootstrap the target set:

```bash
scripts/llmops-admin bootstrap-host --role llm
scripts/llmops-admin bootstrap-host --role agent
```

For manual SSH details and troubleshooting, see
[SSH Setup Runbook](./SSH_SETUP_RUNBOOK.md).

## Staging

Preview selected hosts, local stage paths, remote package directories, and
rendered config destinations without building a package or opening SSH:

```bash
scripts/llmops-admin deploy-plan --dry-run --bundle-id smoke
```

Staging creates a local bundle under:

```text
~/.local/share/llm-ops/stage/<bundle_id>/
```

The stage contains:

- `package/llm-ops-kit.tar.gz`: packaged runtime payload
- `manifest.json`: bundle metadata, target hosts, package checksum, and host config checksums
- `hosts/<host>/config.env`: rendered host config
- `hosts/<host>/config.json`: host-specific JSON config and source metadata
- `hosts/<host>/config-sources.json`: effective config with source reporting

Dry run:

```bash
scripts/llmops-admin stage --dry-run --bundle-id smoke
```

Create a real bundle:

```bash
scripts/llmops-admin stage --bundle-id 20260427-prod
```

`stage` validates the bundle after writing it, including package and host config
checksums.

Validate an existing staged bundle before push or apply:

```bash
scripts/llmops-admin stage-validate --stage ~/.local/share/llm-ops/stage/20260427-prod
```

Limit staging to a host subset when needed:

```bash
scripts/llmops-admin stage --role llm --bundle-id 20260427-llm
scripts/llmops-admin stage --tag production --bundle-id 20260427-prod
```

## Parallel Push

Push transfers the staged package, manifest, and each host's rendered config
to selected hosts. Push runs in parallel and keeps per-host success or failure
isolated.
Before any transfer, `push` validates that the stage contains the package,
manifest, each selected host's env/json config artifacts, and matching
checksums.

Dry run:

```bash
scripts/llmops-admin push --stage ~/.local/share/llm-ops/stage/20260427-prod --dry-run
```

Push with a worker limit:

```bash
scripts/llmops-admin push --stage ~/.local/share/llm-ops/stage/20260427-prod --workers 4
```

If `--stage` is omitted, the newest directory under
`~/.local/share/llm-ops/stage/` is used.

## Remote Apply

Apply runs remote installation commands after a package has been pushed. It:

- creates a release directory under the remote install root
- verifies the pushed package and manifest are present
- verifies pushed host config artifacts are present
- unpacks the pushed package
- copies the pushed manifest into the release directory
- copies host-specific config artifacts into the release directory
- writes `BUNDLE_ID` and `HOST_NAME` marker files into the release directory
- updates the `current` symlink
- preserves the previous install pointer
- installs or refreshes runtime command links
- optionally restarts a selected script
- verifies `modelctl` on `llm` and `hybrid` hosts
- verifies `agentctl` on `agent` and `hybrid` hosts

Before any remote command, `apply` validates that the local stage still has the
manifest and selected host config artifacts used to plan the deployment.

Dry run:

```bash
scripts/llmops-admin apply --stage ~/.local/share/llm-ops/stage/20260427-prod --dry-run
```

Apply in parallel:

```bash
scripts/llmops-admin apply --stage ~/.local/share/llm-ops/stage/20260427-prod --workers 4
```

Optionally restart one deployed script:

```bash
scripts/llmops-admin apply --stage ~/.local/share/llm-ops/stage/20260427-prod --restart modelctl
```

## Configuration Layers

The admin workflow renders host config with deterministic precedence:

```text
global defaults
role defaults
model defaults
profile config
host config
runtime environment
CLI flags
```

Use source reporting to inspect what will be applied:

```bash
scripts/llmops-admin config-settings --host-name llm-primary
scripts/llmops-admin config-settings --role llm --model Qwen3.5
```

Run config validation before staging:

```bash
scripts/llmops-admin config-doctor --role llm --model Qwen3.5
```

The `modelctl` internals still need to be refactored to consume this layered
configuration directly. Track that work in
[Installation Rework Checklist](./INSTALLATION_REWORK_CHECKLIST.md).

## Operational Sequence

Recommended deployment sequence:

```bash
scripts/llmops-admin inventory-validate
scripts/llmops-admin config-doctor --tag production
scripts/llmops-admin bootstrap-host --tag production --dry-run
scripts/llmops-admin bootstrap-host --tag production
scripts/llmops-admin stage --tag production --bundle-id <bundle_id>
scripts/llmops-admin push --tag production --stage ~/.local/share/llm-ops/stage/<bundle_id> --workers 4
scripts/llmops-admin apply --tag production --stage ~/.local/share/llm-ops/stage/<bundle_id> --workers 4
```

Use `--dry-run` before any bootstrap, push, or apply that affects real hosts.

## Related Docs

- [Installation Rework Checklist](./INSTALLATION_REWORK_CHECKLIST.md)
- [SSH Setup Runbook](./SSH_SETUP_RUNBOOK.md)
- [Configuration](./CONFIGURATION.md)
- [modelctl Guide](./MODELCTL_GUIDE.md)
