# Quickstart (10 Minutes)

**Created**: 2026-02-26
**Updated**: 2026-03-10

- [Quickstart (10 Minutes)](#quickstart-10-minutes)
  - [Requirements](#requirements)
  - [Remote Models, Local Gateway](#remote-models-local-gateway)
  - [Fully Local Models and Gateway](#fully-local-models-and-gateway)
  - [Remote sync + deploy](#remote-sync--deploy)
  - [Common checks](#common-checks)

## Requirements

- OpenClaw installed
- `llama-server` at `/usr/local/bin/llama-server`
- Bash 4+ available as `/usr/local/bin/bash` on remote hosts
- `ssh`, `rsync`, `jq`

See `docs/CONFIGURATION.md` for environment overrides before first run.

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
~/bin/install-runtime --source ~/projects/LLM-Ops-Kit
~/bin/gateway start
~/bin/model-proxy restart --upstream http://<remote-model-host>:11434
~/bin/tts-bridge start
```

What `install-runtime` does:

- copies the runtime payload into `~/.llm-ops/current`
- writes runtime state to `~/.llm-ops/runtime-state.env`
- deploys command links into `~/bin`

## Fully Local Models and Gateway

Use this when the LLM, embeddings, MLX TTS server, and OpenClaw all run on the same host.

- Do not bind `model-proxy` or `tts-bridge` to the same local port as the local model server they forward to.
- If you do not need protocol adaptation or tap logging, start the model servers directly and skip the bridge/proxy wrappers.

```bash
~/bin/install-runtime --source ~/projects/LLM-Ops-Kit
~/bin/Qwen3.5 start
~/bin/BGEen start
# Optional:
# ~/bin/Qwen3TTS start
# ~/bin/model-proxy restart --listen-port 11440 --upstream http://127.0.0.1:11434
# ~/bin/tts-bridge start
```

The installed runtime still lives under `~/.llm-ops/current`; `~/bin` only contains links to that installed payload.

## Remote sync + deploy

```bash
~/bin/sync-ops-scripts --delete
```

## Common checks

```bash
~/bin/openclaw-stack status
~/bin/Qwen3 settings
~/bin/BGEen settings
~/bin/model-proxy status
~/bin/tts-bridge status
```

If anything looks off, go to `docs/TROUBLESHOOTING.md`.
