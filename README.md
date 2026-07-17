# LLM-Ops-Kit

LLM-Ops-Kit is a macOS-first local-LAN control layer for models, agents, proxies, bridges, tunnels, dashboards, and supporting services. It coordinates existing processes without containers, model downloads, or agent-specific runtime code.

`llmops` is the only public control command. Components are independently manageable; stacks are named dependency graphs for coordinated operation.

## Supported Platform

- macOS on Apple Silicon
- Python 3.9 or newer
- GNU Bash at `/usr/local/bin/bash`
- SSH for remote hosts
- launchd for supervised services

Linux is not a supported release target.

## Install and Initialize

```bash
/usr/local/bin/bash scripts/install-runtime.sh
~/.local/bin/llmops init --preset single-host
~/.local/bin/llmops doctor --probe
```

Use `--preset local-lan` for separate model and agent hosts. Interactive initialization can discover existing model profiles, normalize selected profiles, and bind chosen chat, embedding, and TTS defaults into disabled starter components. Initialization never starts services.

For deterministic automation:

```bash
llmops init --preset local-lan \
  --model-host model-host.local \
  --agent-host agent-host.local \
  --model-defaults-from ~/.config/llm-ops \
  --import-model ChatModel \
  --import-model EmbeddingModel \
  --default-chat ChatModel \
  --default-embedding EmbeddingModel
```

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

## Configuration and Migration

Canonical JSON lives under `~/.config/llm-ops/`. Runtime releases consume their bundled role-filtered configuration snapshot unless `LLMOPS_CONFIG_HOME` explicitly selects another root.

The runtime never reads proof-of-concept shell configuration. Use a reviewed one-way migration:

```bash
llmops migrate-config --legacy-home ~/.llm-ops --dry-run --json
llmops migrate-config --legacy-home ~/.llm-ops
llmops doctor --probe
```

Environment variables are limited to path selection, explicit secret injection, and documented emergency overrides. `LLMOPS_ENV_FILE` is an explicit secret-injection boundary, not a configuration source.

## Deployment

The administrator checkout is the one-way desired-state authority. Deployment packages tracked runtime code and one role-filtered JSON snapshot into an immutable release per host.

```bash
llmops deploy --bundle-id <release> --dry-run
llmops deploy --bundle-id <release>
llmops drift --stage ~/.local/share/llm-ops/stage/<release>
llmops rollback
```

Dirty deployment sources are refused unless `--allow-dirty` is explicitly supplied and recorded.

## Documentation

- [Quickstart](docs/QUICKSTART.md)
- [Configuration](docs/CONFIGURATION.md)
- [Migration](docs/MIGRATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT_OVERVIEW.md)
- [Upgrade and rollback](docs/UPGRADE_AND_ROLLBACK.md)
- [Model profiles](docs/MODELCTL_GUIDE.md)
- [Model proxy](docs/PROXY_TAP_RUNBOOK.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## License

See [LICENSE.md](LICENSE.md).
