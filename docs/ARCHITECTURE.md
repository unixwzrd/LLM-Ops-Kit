# Architecture Overview

**Created**: 2026-02-26
**Updated**: 2026-03-01

- [Architecture Overview](#architecture-overview)
  - [Components](#components)
  - [Flow](#flow)
  - [Script architecture](#script-architecture)
  - [Deployment model](#deployment-model)

## Components

- OpenClaw runtime (`gateway`)
- Model proxy wrapper (`model-proxy`) + tap (`model-proxy-tap`)
- TTS service (`tts` via `mlx_audio.server`)
- LLM service (`Qwen3` / `Qwen3.5` via `llama-server`)
- Embedding service (`BGEen` via `llama-server --embedding`)
- Operator scripts (`LLM-Ops-Kit/scripts`)

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

- Source of truth: `~/projects/LLM-Ops-Kit`
- Runtime command surface: `~/bin`
- Cross-host updates via `sync-ops-scripts` + deploy/verify link scripts.
