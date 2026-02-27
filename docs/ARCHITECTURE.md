# Architecture Overview

**Created**: 2026-02-26
**Updated**: 2026-02-26

## Components

- OpenClaw runtime (`gateway`)
- OpenAI proxy tap (`proxy`)
- LLM service (`Qwen3` / `Qwen3.5` via `llama-server`)
- Embedding service (`BGEen` via `llama-server --embedding`)
- Operator scripts (`agent-work/scripts`)

## Flow

1. User/channel input enters OpenClaw gateway.
2. Gateway routes model calls through proxy tap (when enabled).
3. LLM inference served by local/remote `llama-server` profile.
4. Memory search/indexing uses embedding service profile.
5. Operator controls lifecycle via `~/bin/*` symlink commands.

## Script architecture

- `scripts/modelctl`: core launcher logic for model profiles.
- `scripts/models/*.sh`: model-specific defaults.
- `scripts/defaults/*.sh`: model-type/global fallback defaults.
- `scripts/runtime-links.manifest`: single source for runtime command links.

## Deployment model

- Source of truth: `~/projects/agent-work`
- Runtime command surface: `~/bin`
- Cross-host updates via `sync-agent-work` + deploy/verify link scripts.
