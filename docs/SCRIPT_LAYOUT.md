# Script Layout (Canonical)

**Created**: 2026-02-20
**Updated**: 2026-03-01

Canonical script home:

- `~/projects/LLM-Ops-Kit/scripts`
- `~/projects/LLM-Ops-Kit/bin`

Runtime command surface:

- `~/bin/*` symlinks point to canonical scripts in `~/projects/LLM-Ops-Kit/scripts` (or selected helper binaries in `~/projects/LLM-Ops-Kit/bin`).
- Managed commands include: `gateway`, `proxy`, `tts`, `Qwen3`, `Qwen3.5`, `Qwen3TTS`, `BGEen`, `openclaw-stack`, `openclaw-report`, `sync-ops-scripts`, `openai-proxy-tap`.

Notes:

- Deployment/link management is intentionally scoped to `~/bin` for portability.
- `.openclaw` and `OpenClaw-workspace` remain local operational repos.
- Canonical docs/planning/scripts now live under `LLM-Ops-Kit`.
