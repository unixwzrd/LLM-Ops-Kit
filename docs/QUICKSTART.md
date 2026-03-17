# Quickstart (10 Minutes)

**Created**: 2026-02-26
**Updated**: 2026-03-13

- [Quickstart (10 Minutes)](#quickstart-10-minutes)
  - [Requirements](#requirements)
  - [Remote Models, Local Gateway](#remote-models-local-gateway)
  - [Fully Local Models and Gateway](#fully-local-models-and-gateway)
  - [Remote sync + deploy](#remote-sync--deploy)
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

## First-Time Install

Clone the repo first, then install the runtime from that checkout:

```bash
git clone https://github.com/unixwzrd/LLM-Ops-Kit.git ~/projects/LLM-Ops-Kit
cd ~/projects/LLM-Ops-Kit
./scripts/install-runtime --source "$PWD"
```

After that, use the linked commands in `~/bin`.

## Remote Models, Local Gateway

Use this when OpenClaw, `gateway`, `model-proxy`, and `tts-bridge` run locally, while the LLM, embeddings, and MLX TTS run on a remote model host.

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
~/bin/gateway start
~/bin/model-proxy restart --upstream http://<remote-model-host>:11434
~/bin/tts-bridge start
```

What `install-runtime` does:

- copies the runtime payload into `~/.llm-ops/current`
- writes runtime state to `~/.llm-ops/runtime-state.env`
- deploys command links into `~/bin`

Optional `Secrets Kit` setup:

```bash
cat >> ~/.llm-ops/config.env <<'EOF'
LLMOPS_USE_SECKIT=1
LLMOPS_SECKIT_SERVICE=openclaw
LLMOPS_SECKIT_ACCOUNT=miafour
EOF
```

When enabled, wrappers such as `gateway`, `model-proxy`, and `tts-bridge` will import secret values from `seckit` automatically during startup.

Important:

- Do not start wrappers with `bash -x` or `set -x` when `LLMOPS_USE_SECKIT=1`.
- Shell tracing can expose exported secret values in terminal output or logs.

Current stabilization mode on the primary operator machine:

- `gateway` runs in direct-run mode through the wrapper, not through `openclaw gateway start`
- runtime `seckit` loading is currently disabled for startup (`LLMOPS_USE_SECKIT=0`)
- live logs are:
  - wrapper stdio: `~/.llm-ops/logs/gateway.log` and `~/.llm-ops/logs/gateway.err.log`
  - OpenClaw app log: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
- `openclaw logs --follow`, `openclaw gateway probe`, and `openclaw gateway health` may still fail even when the gateway itself is up in this mode
- use `~/bin/gateway logs` for a reliable local follow view during this phase

## Fully Local Models and Gateway

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

The installed runtime still lives under `~/.llm-ops/current`; `~/bin` only contains links to that installed payload.

## Remote sync + deploy

```bash
cd ~/projects/LLM-Ops-Kit
~/bin/sync-ops-scripts --delete
```

## Common checks

```bash
~/bin/openclaw-stack status
~/bin/gateway status
~/bin/gateway logs
~/bin/Qwen3 settings
~/bin/BGEm3 settings
~/bin/model-proxy status
~/bin/tts-bridge status
```

If anything looks off, go to `docs/TROUBLESHOOTING.md`.
