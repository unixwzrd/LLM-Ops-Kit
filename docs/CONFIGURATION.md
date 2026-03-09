# Configuration Guide

**Created**: 2026-02-28  
**Updated**: 2026-03-08

- [Configuration Guide](#configuration-guide)
  - [What This Doc Is For](#what-this-doc-is-for)
  - [When to Use This Guide](#when-to-use-this-guide)
  - [Related Docs](#related-docs)
  - [Configuration Precedence](#configuration-precedence)
  - [Core Environment Variables](#core-environment-variables)
  - [Sync Variables](#sync-variables)
  - [Example `.env.local`](#example-envlocal)
  - [Local Example (Current Operator Setup)](#local-example-current-operator-setup)
  - [Remote/Portable Example](#remoteportable-example)
  - [Optional: Secrets Kit Integration](#optional-secrets-kit-integration)
  - [Bootstrapping](#bootstrapping)

## What This Doc Is For

This guide is the runtime configuration reference for LLM-Ops-Kit.

Use it to:

- Decide which host/port/path values your scripts should use
- Override defaults without editing scripts
- Configure sync behavior across local and remote hosts
- Move sensitive values to an external secrets manager instead of `.env` files

If you are only trying to start services quickly, use [QUICKSTART](./QUICKSTART.md) first.

## When to Use This Guide

Use this file when you are:

- Setting up a new machine or VM
- Changing upstream LLM/TTS host or ports
- Migrating repo paths
- Standardizing settings before publishing docs/scripts

## Related Docs

- Main index: [`README`](../README.md)
- Quickstart: [`QUICKSTART`](./QUICKSTART.md)
- Sync/deploy workflow: [`DEPLOYMENT_SYNC_RUNBOOK`](./DEPLOYMENT_SYNC_RUNBOOK.md)
- Template env file: [`.env.example`](../.env.example)
- TTS API setup: [`MLX_AUDIO_TTS_GUIDE`](./MLX_AUDIO_TTS_GUIDE.md)

## Configuration Precedence

Scripts use this precedence:

1. CLI flags (when supported)
2. Exported environment variables
3. `~/.llm-ops/config.env` user config
4. Repo defaults (`scripts/config/hosts.env`)
5. Script defaults

Note:
- Toolkit scripts do not rely on `~/.openclaw/.env` by default.
- Keep toolkit configuration in `~/.llm-ops/config.env`.

## Core Environment Variables

- `~/.llm-ops/config.env`: user-owned toolkit config file for host/IP/path overrides.
- `LLMOPS_HOME`: toolkit state root (default `~/.llm-ops`).
- `LLMOPS_RUN_DIR`: runtime pid/state dir (default `$LLMOPS_HOME/run`).
- `LLMOPS_LOG_DIR`: toolkit log dir (default `$LLMOPS_HOME/logs`).
- `LLMOPS_ROOT`: canonical runtime asset root, resolved from the installed runtime payload or explicit override.
- `scripts/config/hosts.env`: centralized default host/IP file for wrappers (sync/model-proxy) in the active runtime payload.
- `LLMOPS_UPSTREAM_HOST`: default upstream model host for wrappers.
- `LLMOPS_SYNC_HOST`: optional dedicated sync host override (falls back to `LLMOPS_UPSTREAM_HOST`).
- `LLMOPS_UPSTREAM_PORT`: default upstream model port for wrappers.
- `MODEL_PROXY_LISTEN_HOST`: default bind host for proxy wrappers.
- `MODEL_PROXY_LISTEN_PORT`: default bind port for proxy wrappers.
- `MODEL_PROXY_TAP_BIN`: optional explicit path to `model-proxy-tap`.
- `OPENAI_TTS_BASE_URL`: OpenClaw OpenAI-TTS provider base URL (for example `http://127.0.0.1:11440/v1`).
- `TTS_BRIDGE_HOST`: bind host for `tts-bridge`.
- `TTS_BRIDGE_PORT`: bind port for `tts-bridge`.
- `TTS_BRIDGE_UPSTREAM_BASE`: upstream MLX Audio base URL.
- `TTS_BRIDGE_MODEL`: default model path injected by bridge.
- `TTS_BRIDGE_VOICE`: default voice injected by bridge. Required fallback for `CustomVoice` bridge setups unless the caller always sends `voice`.
- `TTS_BRIDGE_REF_AUDIO`: default reference audio file.
- `TTS_BRIDGE_REF_TEXT`: default reference transcript file (or literal text if passed directly).
- `TTS_BRIDGE_PYTHON_BIN`: python binary used by bridge launcher.
- `LLMOPS_LOG_ROTATE_BYTES`: rotate active logs after this many bytes.
- `LLMOPS_LOG_ROTATE_KEEP`: number of rotated logs to keep per active log.
- `LLMOPS_LOG_ROTATE_MAX_AGE_DAYS`: optional max age for rotated logs.
- `LLMOPS_BACKUP_KEEP`: number of runtime install backups to keep.
- `LLMOPS_BACKUP_MAX_AGE_DAYS`: optional max age for runtime install backups.

## Sync Variables

- `SYNC_HOST`
- `SYNC_USER`
- `SYNC_REMOTE_DIR`
- `SYNC_LOCAL_DIR`
- `SYNC_KEY_PATH`
- `SYNC_KEY_TTL`

## Example `.env.local`

```bash
# Copy from .env.example and adapt values.
LLMOPS_UPSTREAM_HOST=<upstream-host>
LLMOPS_UPSTREAM_PORT=<upstream-port>
MODEL_PROXY_LISTEN_HOST=127.0.0.1
MODEL_PROXY_LISTEN_PORT=<listen-port>
LLMOPS_HOME=~/.llm-ops
LLMOPS_RUN_DIR=~/.llm-ops/run
LLMOPS_LOG_DIR=~/.llm-ops/logs
LLMOPS_LOG_ROTATE_BYTES=10485760
LLMOPS_LOG_ROTATE_KEEP=5
LLMOPS_BACKUP_KEEP=5

SYNC_HOST=<sync-host>
SYNC_USER=<your-user>
SYNC_REMOTE_DIR=~/projects/LLM-Ops-Kit
SYNC_LOCAL_DIR=~/projects/LLM-Ops-Kit/
```

## Local Example (Examples Only)

```bash
export LLMOPS_UPSTREAM_HOST="<example-upstream-host>"
export LLMOPS_UPSTREAM_PORT="11434"
export MODEL_PROXY_LISTEN_HOST="127.0.0.1"
export MODEL_PROXY_LISTEN_PORT="11434"
```

## Remote/Portable Example (Examples Only)

```bash
export LLMOPS_UPSTREAM_HOST="<upstream-host>"
export LLMOPS_UPSTREAM_PORT="<upstream-port>"
export MODEL_PROXY_LISTEN_HOST="127.0.0.1"
export MODEL_PROXY_LISTEN_PORT="<listen-port>"
```

## Optional: Secrets Kit Integration

If you do not want sensitive values in `.env` files, use `seckit` and export values into the runtime shell.

Project:

- `seckit` (set to your canonical repo URL once published)
- Example URL: `https://github.com/unixwzrd/seckit`

Example flow:

```bash
# 1) Install (example from GitHub)
python -m pip install "git+https://github.com/unixwzrd/seckit.git"

# 2) Store values
seckit set --name LLMOPS_UPSTREAM_HOST --value <example-upstream-host> --service openclaw --account default
seckit set --name LLMOPS_UPSTREAM_PORT --value 11434 --service openclaw --account default
seckit set --name MODEL_PROXY_LISTEN_HOST --value 127.0.0.1 --service openclaw --account default
seckit set --name MODEL_PROXY_LISTEN_PORT --value 11434 --service openclaw --account default

# 3) Export at runtime
eval "$(seckit export --format shell --service openclaw --account default)"

# 4) Start stack with exported settings
~/bin/openclaw-stack restart all
```

Notes:

- Keep `.env` for non-sensitive defaults and local convenience.
- Keep tokens/secrets in `seckit` only.

## Bootstrapping

Use [`.env.example`](../.env.example) as a starting template for your local environment values.

Recommended user-owned config path:

```bash
mkdir -p ~/.llm-ops
cat > ~/.llm-ops/config.env <<'EOF'
LLMOPS_UPSTREAM_HOST=<example-upstream-host>
LLMOPS_SYNC_HOST=<example-upstream-host>
LLMOPS_UPSTREAM_PORT=11434
MODEL_PROXY_LISTEN_HOST=127.0.0.1
MODEL_PROXY_LISTEN_PORT=11434
LLMOPS_HOME=$HOME/.llm-ops
LLMOPS_RUN_DIR=$HOME/.llm-ops/run
LLMOPS_LOG_DIR=$HOME/.llm-ops/logs
LLMOPS_LOG_ROTATE_BYTES=10485760
LLMOPS_LOG_ROTATE_KEEP=5
LLMOPS_BACKUP_KEEP=5
EOF
```
