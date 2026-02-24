# Script Layout (Canonical)

Canonical script home:
- `~/projects/agent-work/scripts`
- `~/projects/agent-work/bin`

Runtime command surface:
- `~/bin/*` symlinks point to canonical scripts in `~/projects/agent-work/scripts` (or selected helper binaries in `~/projects/agent-work/bin`).
- Managed commands include: `gateway`, `proxy`, `Qwen3`, `BGEen`, `openclaw-stack`, `openclaw-report`, `sync-agent-work`, `openai-proxy-tap`, `node-hygiene`.

Notes:
- Deployment/link management is intentionally scoped to `~/bin` for portability.
- `.openclaw` and `OpenClaw-workspace` remain local operational repos.
- Canonical docs/planning/scripts now live under `agent-work`.
