# Configuration Guide

**Created**: 2026-02-28  
**Updated**: 2026-03-02

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
3. Script defaults (kept backward-compatible for current local setup)

## Core Environment Variables

- `scripts/config/hosts.env`: centralized default host/IP file for wrappers (sync/proxy) in this repo.
- `OPENCLAW_AGENT_WORK_ROOT`: canonical repo root used for template/tool paths.
- `OPENCLAW_UPSTREAM_HOST`: default upstream model host for wrappers.
- `OPENCLAW_SYNC_HOST`: optional dedicated sync host override (falls back to `OPENCLAW_UPSTREAM_HOST`).
- `OPENCLAW_UPSTREAM_PORT`: default upstream model port for wrappers.
- `OPENCLAW_PROXY_LISTEN_HOST`: default bind host for proxy wrappers.
- `OPENCLAW_PROXY_LISTEN_PORT`: default bind port for proxy wrappers.
- `OPENCLAW_PROXY_TAP_BIN`: optional explicit path to `openai-proxy-tap`.
- `OPENAI_TTS_BASE_URL`: OpenClaw OpenAI-TTS provider base URL (for example `http://127.0.0.1:11440/v1`).
- `TTS_BRIDGE_HOST`: bind host for `tts-bridge`.
- `TTS_BRIDGE_PORT`: bind port for `tts-bridge`.
- `TTS_BRIDGE_UPSTREAM_BASE`: upstream MLX Audio base URL.
- `TTS_BRIDGE_MODEL`: default model path injected by bridge.
- `TTS_BRIDGE_VOICE`: default voice injected by bridge.
- `TTS_BRIDGE_REF_AUDIO`: default reference audio file.
- `TTS_BRIDGE_REF_TEXT`: default reference transcript file (or literal text if passed directly).
- `TTS_BRIDGE_PYTHON_BIN`: python binary used by bridge launcher.

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
OPENCLAW_AGENT_WORK_ROOT=~/projects/LLM-Ops-Kit
OPENCLAW_UPSTREAM_HOST=<upstream-host>
OPENCLAW_UPSTREAM_PORT=<upstream-port>
OPENCLAW_PROXY_LISTEN_HOST=127.0.0.1
OPENCLAW_PROXY_LISTEN_PORT=<listen-port>

SYNC_HOST=<sync-host>
SYNC_USER=<your-user>
SYNC_REMOTE_DIR=~/projects/LLM-Ops-Kit
SYNC_LOCAL_DIR=~/projects/LLM-Ops-Kit/
```

## Local Example (Current Operator Setup)

```bash
export OPENCLAW_AGENT_WORK_ROOT="$HOME/projects/LLM-Ops-Kit"
export OPENCLAW_UPSTREAM_HOST="172.20.10.2"
export OPENCLAW_UPSTREAM_PORT="11434"
export OPENCLAW_PROXY_LISTEN_HOST="127.0.0.1"
export OPENCLAW_PROXY_LISTEN_PORT="11434"
```

## Remote/Portable Example

```bash
export OPENCLAW_AGENT_WORK_ROOT="$HOME/projects/LLM-Ops-Kit"
export OPENCLAW_UPSTREAM_HOST="<upstream-host>"
export OPENCLAW_UPSTREAM_PORT="<upstream-port>"
export OPENCLAW_PROXY_LISTEN_HOST="127.0.0.1"
export OPENCLAW_PROXY_LISTEN_PORT="<listen-port>"
```

## Optional: Secrets Kit Integration

If you do not want sensitive values in `.env` files, use `seckit` and export values into the runtime shell.

Project:

- `seckit` (set to your canonical repo URL once published)
- Example URL: `https://github.com/unixwzrd/seckit`

Example flow:

```bash
# 1) Install (example from GitHub)
python3 -m pip install "git+https://github.com/unixwzrd/seckit.git"

# 2) Store values
seckit set --name OPENCLAW_UPSTREAM_HOST --value 172.20.10.2 --service openclaw --account default
seckit set --name OPENCLAW_UPSTREAM_PORT --value 11434 --service openclaw --account default
seckit set --name OPENCLAW_PROXY_LISTEN_HOST --value 127.0.0.1 --service openclaw --account default
seckit set --name OPENCLAW_PROXY_LISTEN_PORT --value 11434 --service openclaw --account default

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
