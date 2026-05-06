# Quickstart (10 Minutes)

Back: [docs/INDEX.md](./INDEX.md)

**Created**: 2026-02-26
**Updated**: 2026-04-27

- [Quickstart (10 Minutes)](#quickstart-10-minutes)
  - [Requirements](#requirements)
  - [Remote Models, Local Agent Runtime](#remote-models-local-agent-runtime)
  - [Fully Local Models and Agent Runtime](#fully-local-models-and-agent-runtime)
- [Admin Deployment](#admin-deployment)
  - [Common checks](#common-checks)

## Requirements

- OpenClaw installed
- Python 3.9+ with `jinja2` available for prompt/template helpers
- `llama-server` at `/usr/local/bin/llama-server`
- `mlx-audio` installed on the TTS host if you are using the MLX TTS path
- Bash 4+ available as `/usr/local/bin/bash` on remote hosts
- `ssh`, `rsync`, `jq`

See `docs/CONFIGURATION.md` for environment overrides before first run.

Minimal Python bootstrap:

```bash
python3 -m pip install jinja2
```

## First-Time Admin Deploy

Clone the repo first, then validate the inventory and stage a deployment bundle
from the administrator workstation:

```bash
git clone https://github.com/unixwzrd/LLM-Ops-Kit.git ~/projects/LLM-Ops-Kit
cd ~/projects/LLM-Ops-Kit
scripts/llmops-admin inventory-validate
scripts/llmops-admin bootstrap-host --dry-run
scripts/llmops-admin stage --dry-run --bundle-id smoke
```

The admin workflow is inventory based. Edit `~/.llm-ops/inventory.yml` for live
targets, or start from `deploy/inventory.yml`.

For the full deployment sequence, see
[Deployment Overview](./DEPLOYMENT_OVERVIEW.md).

Deployment work should use `llmops-admin` from the administrator workstation.
Lower-level packaging and transport helpers are implementation details, not a
separate operator workflow.

## Remote Models, Local Agent Runtime

Use this when OpenClaw, `agentctl`, `model-proxy`, and `tts-bridge` run locally, while the LLM, embeddings, and MLX TTS run on a remote model host.

Set these first in `~/.llm-ops/config.env`:

```bash
export LLMOPS_UPSTREAM_HOST=<remote-model-host>
export LLMOPS_UPSTREAM_PORT=11434
export LLMOPS_SYNC_HOST=<remote-model-host>
export MODEL_PROXY_LISTEN_HOST=127.0.0.1
export MODEL_PROXY_LISTEN_PORT=11434
export TTS_BRIDGE_PORT=11439
export TTS_BRIDGE_UPSTREAM_BASE=http://<remote-model-host>:11439/v1
```

```bash
cd ~/projects/LLM-Ops-Kit
~/bin/agentctl start
~/bin/model-proxy restart --upstream http://<remote-model-host>:11434
~/bin/tts-bridge start
```

What admin deployment does:

- builds a local package under `~/.llm-ops/stage/<bundle_id>/`
- renders per-host config from inventory and layered config
- pushes the package and config to selected hosts in parallel
- applies the package on each remote host
- updates runtime links and verifies the role-specific command surface

Optional `Secrets Kit` setup:

```bash
cat >> ~/.llm-ops/config.env <<'EOF'
LLMOPS_USE_SECKIT=1
LLMOPS_SECKIT_SERVICE=openclaw
LLMOPS_SECKIT_ACCOUNT=miafour
EOF
```

When enabled, wrappers such as `agentctl`, `model-proxy`, and `tts-bridge` will import secret values from `seckit` automatically during startup.

Important:

- Do not start wrappers with `bash -x` or `set -x` when `LLMOPS_USE_SECKIT=1`.
- Shell tracing can expose exported secret values in terminal output or logs.

Current stabilization mode on the primary operator machine:

- `agentctl` runs in direct-run mode through the wrapper instead of the native OpenClaw service entrypoint
- runtime `seckit` loading is currently disabled for startup (`LLMOPS_USE_SECKIT=0`)
- live logs are:
  - wrapper stdio: `~/.llm-ops/logs/agentctl-openclaw.log` and `~/.llm-ops/logs/agentctl-openclaw.err.log`
  - OpenClaw app log: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
- `openclaw logs --follow` and related native health/probe commands may still fail even when the agent runtime itself is up in this mode
- use `~/bin/agentctl logs` for a reliable local follow view during this phase

## Fully Local Models and Agent Runtime

Use this when the LLM, embeddings, MLX TTS server, and OpenClaw all run on the same host.

- Do not bind `model-proxy` or `tts-bridge` to the same local port as the local model server they forward to.
- If you do not need protocol adaptation or tap logging, start the model servers directly and skip the bridge/proxy wrappers.

```bash
cd ~/projects/LLM-Ops-Kit
~/bin/Qwen3.5 start
~/bin/BGEm3 start
# Optional:
# ~/bin/Qwen3TTS start
# ~/bin/model-proxy restart --listen-port 11440 --upstream http://127.0.0.1:11434
# ~/bin/tts-bridge start
```

The deployed runtime still lives under the configured install prefix, typically `~/.llm-ops/current`; the target `~/bin` only contains links to that installed payload.

## Admin Deployment

```bash
cd ~/projects/LLM-Ops-Kit
scripts/llmops-admin inventory-validate
scripts/llmops-admin config-doctor --tag production
scripts/llmops-admin bootstrap-host --tag production --dry-run
scripts/llmops-admin stage --tag production --bundle-id <bundle_id>
scripts/llmops-admin push --tag production --stage ~/.llm-ops/stage/<bundle_id> --workers 4
scripts/llmops-admin apply --tag production --stage ~/.llm-ops/stage/<bundle_id> --workers 4
```

## Common checks

```bash
~/bin/agentctl status
~/bin/agentctl logs
~/bin/modelctl status
~/bin/Qwen3 settings
~/bin/BGEm3 settings
~/bin/model-proxy status
~/bin/tts-bridge status
```

If anything looks off, go to `docs/TROUBLESHOOTING.md`.

## See Also

- [How It Works](./HOW_IT_WORKS.md)
- [Switching Models and Agents](./SWITCHING.md)
- [Configuration](./CONFIGURATION.md)
