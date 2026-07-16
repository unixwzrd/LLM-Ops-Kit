# LLM-Ops-Kit

LLM-Ops-Kit is a macOS-first operations toolkit for running models, agents, proxies, bridges, tunnels, dashboards, and supporting services on one Apple Silicon Mac or across a local LAN.

It provides dependency-aware component control without requiring Docker or Kubernetes. Components remain independently manageable; stacks are named dependency groupings for coordinated operations.

## Supported Platform

- macOS on Apple Silicon
- Python 3.9 or newer
- Bash 3.2 compatibility for runtime wrappers
- SSH for LAN operation
- launchd for supervised macOS services

Linux is not a supported or tested platform for this release.

## Main Commands

```bash
llmops init --preset single-host
llmops doctor
llmops config show --json
llmops plan --action start

llmops component list
llmops component plan restart <component>
llmops component start <component>
llmops component stop <component> [--force|--cascade]
llmops component restart <component> [--cascade]
llmops component status <component>
llmops component logs <component>

llmops stack list
llmops stack plan start <stack>
llmops stack start <stack>
llmops stack stop <stack>
llmops stack restart <stack>
llmops stack status <stack>

llmops deploy --config-home ~/.config/llm-ops
llmops drift
llmops rollback
```

Every lifecycle operation has a non-mutating plan form. Component restart affects only the selected component by default. `--cascade` includes active dependents in dependency-safe order.

## Configuration

Authoritative JSON configuration lives under `~/.config/llm-ops/`:

```text
config.json
inventory.json
stacks/*.json
models/*.json
agents/*.json
services/*.json
```

Run `llmops init --preset single-host` or `llmops init --preset local-lan` to create a disabled starter configuration. Initialization refuses to overwrite existing files unless `--force` is supplied.

Real topology, credentials, model paths, and host profiles should remain untracked. Sanitized examples are under [`docs/examples`](docs/examples).

## Agent Independence

Hermes and OpenClaw are compatibility adapters, not implicit defaults. No agent starts unless an agent component or explicit compatibility target is configured. Other agents use generic process, launchd, or explicitly enabled argv-based command profiles.

## Deployment

The administrator checkout is the one-way desired-state authority. An authoritative deployment creates a checksummed package plus a role-filtered configuration snapshot for each host, pushes both, and applies them as one immutable release.

The active release is selected by `<install_root>/current`; the prior release is retained at `<install_root>/previous`. `llmops rollback` atomically exchanges those pointers and refreshes managed runtime links.

Dirty deployments are refused by default. Use `--allow-dirty` only for an intentional canary; the manifest records the dirty state, Git commit, toolkit version, and content hashes.

## Included Runtime Tools

- `modelctl` for model runner profiles
- `model-proxy` for request tapping, prompt rendering, and upstream routing
- `tts-bridge` for stable voice names and TTS request adaptation
- `agentctl` compatibility adapters for Hermes and OpenClaw
- immutable deployment, drift reporting, rollback, and runtime maintenance

## Documentation

- [Quickstart](docs/QUICKSTART.md)
- [Configuration](docs/CONFIGURATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT_OVERVIEW.md)
- [Upgrade and Rollback](docs/UPGRADE_AND_ROLLBACK.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Documentation Index](docs/INDEX.md)

## Optional UI Direction

The CLI and shared Python control modules are the authoritative orchestration interfaces. A future optional UI may use a separate loopback-only FastAPI process with static HTML, CSS, vanilla JavaScript, REST commands, and SSE events. It must remain usable while every model and agent is stopped and must not initialize model engines.

## License

See [LICENSE](LICENSE).
