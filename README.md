# LLM-Ops-Kit

**Created**: 2026-02-20
**Updated**: 2026-07-16

LLM-Ops-Kit is a macOS-first, local-LAN control layer for models, agents, proxies, bridges, tunnels, dashboards, and supporting services. It coordinates existing processes without Docker, Kubernetes, model downloads, or agent-specific runtime code.

`llmops` is the only public control command. A component is independently manageable. A stack is a named dependency graph used for coordinated operation.

## Supported Platform

- macOS on Apple Silicon
- Python 3.9 or newer
- GNU Bash available as `/usr/local/bin/bash`
- SSH for remote hosts
- launchd for supervised services

Linux is not a supported release target.

## Install

```bash
/usr/local/bin/bash scripts/install-runtime.sh
~/.local/bin/llmops init --preset single-host
~/.local/bin/llmops doctor
```

Use `--preset local-lan` for separate model and agent hosts. Initialization creates disabled examples and never starts services.

## Operate

```bash
llmops component list
llmops component plan restart <component>
llmops component start <component>
llmops component restart <component>
llmops component stop <component> [--force|--cascade]
llmops component status <component>
llmops component logs <component>

llmops stack list
llmops stack plan start <stack>
llmops stack start <stack>
llmops stack stop <stack>
llmops stack restart <stack>
llmops stack status <stack>
```

Starting a component starts missing dependencies. Restarting affects only the requested component unless `--cascade` is supplied. Stopping a component with active dependents requires `--force` or `--cascade`.

## Configuration

Canonical JSON lives under `~/.config/llm-ops/`:

```text
config.json
inventory.json
stacks/*.json
models/*.json
agents/*.json
services/*.json
```

The runtime never reads proof-of-concept shell configuration. Use `llmops migrate-config --legacy-home ~/.llm-ops` once, review the JSON, then remove the old configuration from operation.

Environment variables are limited to path selection, explicit secret injection, and documented emergency process overrides. An optional `LLMOPS_ENV_FILE` is a secret-injection boundary, not a configuration source.

## Deployment

The administrator checkout is the one-way desired-state authority. `llmops deploy` packages code and a role-filtered JSON snapshot into one immutable release per host. `current` selects the active release and `previous` retains the rollback target.

```bash
llmops deploy --config-home ~/.config/llm-ops --bundle-id <release> --dry-run
llmops deploy --config-home ~/.config/llm-ops --bundle-id <release>
llmops drift --stage ~/.local/share/llm-ops/stage/<release>
llmops rollback
```

Deployment refuses dirty source by default. `--allow-dirty` is intended only for a deliberate canary and is recorded in the manifest.

## Documentation

- [Documentation index](docs/INDEX.md)
- [Quickstart](docs/QUICKSTART.md)
- [Configuration](docs/CONFIGURATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT_OVERVIEW.md)
- [Upgrade and rollback](docs/UPGRADE_AND_ROLLBACK.md)
- [Model profiles](docs/MODELCTL_GUIDE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## License

See [LICENSE.md](LICENSE.md).
