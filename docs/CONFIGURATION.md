# Configuration Guide

**Created**: 2026-02-28  
**Updated**: 2026-03-01

- [Configuration Guide](#configuration-guide)
  - [Purpose](#purpose)
  - [Related Docs](#related-docs)
  - [Override Model](#override-model)
  - [Core Environment Variables](#core-environment-variables)
  - [Sync Variables](#sync-variables)
  - [Example `.env.local`](#example-envlocal)
  - [Local Example (Current Operator Setup)](#local-example-current-operator-setup)
  - [Remote/Portable Example](#remoteportable-example)
  - [Bootstrapping](#bootstrapping)

## Purpose

Define runtime defaults and environment overrides without requiring script edits.

## Related Docs

- Main index: [`README.md`](../README.md)
- Quickstart: [`QUICKSTART.md`](./QUICKSTART.md)
- Sync/deploy workflow: [`DEPLOYMENT_SYNC_RUNBOOK.md`](./DEPLOYMENT_SYNC_RUNBOOK.md)
- Template env file: [`.env.example`](../.env.example)

## Override Model

Scripts use this precedence:

1. CLI flags (when supported)
2. Exported environment variables
3. Script defaults (kept backward-compatible for current local setup)

## Core Environment Variables

- `OPENCLAW_AGENT_WORK_ROOT`: canonical repo root used for template/tool paths.
- `OPENCLAW_UPSTREAM_HOST`: default upstream model host for wrappers.
- `OPENCLAW_UPSTREAM_PORT`: default upstream model port for wrappers.
- `OPENCLAW_PROXY_LISTEN_HOST`: default bind host for proxy wrappers.
- `OPENCLAW_PROXY_LISTEN_PORT`: default bind port for proxy wrappers.
- `OPENCLAW_PROXY_TAP_BIN`: optional explicit path to `openai-proxy-tap`.

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
OPENCLAW_AGENT_WORK_ROOT=~/projects/OpenClaw-Ops-Toolkit
OPENCLAW_UPSTREAM_HOST=<upstream-host>
OPENCLAW_UPSTREAM_PORT=<upstream-port>
OPENCLAW_PROXY_LISTEN_HOST=127.0.0.1
OPENCLAW_PROXY_LISTEN_PORT=<listen-port>

SYNC_HOST=<sync-host>
SYNC_USER=<your-user>
SYNC_REMOTE_DIR=~/projects/OpenClaw-Ops-Toolkit
SYNC_LOCAL_DIR=~/projects/OpenClaw-Ops-Toolkit/
```

## Local Example (Current Operator Setup)

```bash
export OPENCLAW_AGENT_WORK_ROOT="$HOME/projects/OpenClaw-Ops-Toolkit"
export OPENCLAW_UPSTREAM_HOST="10.0.0.67"
export OPENCLAW_UPSTREAM_PORT="11434"
export OPENCLAW_PROXY_LISTEN_HOST="127.0.0.1"
export OPENCLAW_PROXY_LISTEN_PORT="11434"
```

## Remote/Portable Example

```bash
export OPENCLAW_AGENT_WORK_ROOT="$HOME/projects/OpenClaw-Ops-Toolkit"
export OPENCLAW_UPSTREAM_HOST="<upstream-host>"
export OPENCLAW_UPSTREAM_PORT="<upstream-port>"
export OPENCLAW_PROXY_LISTEN_HOST="127.0.0.1"
export OPENCLAW_PROXY_LISTEN_PORT="<listen-port>"
```

## Bootstrapping

Use [`.env.example`](../.env.example) as a starting template for your local environment values.
