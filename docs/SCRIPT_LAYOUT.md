# Script Layout (Canonical)

**Created**: 2026-02-20
**Updated**: 2026-02-26

Canonical script home:

- `~/projects/OpenClaw-Ops-Toolkit/scripts`
- `~/projects/OpenClaw-Ops-Toolkit/bin`

Runtime command surface:

- `~/bin/*` symlinks point to canonical scripts in `~/projects/OpenClaw-Ops-Toolkit/scripts` (or selected helper binaries in `~/projects/OpenClaw-Ops-Toolkit/bin`).
- Managed commands include: `gateway`, `proxy`, `Qwen3`, `BGEen`, `openclaw-stack`, `openclaw-report`, `sync-ops-scripts`, `openai-proxy-tap`, `node-hygiene`.

Notes:

- Deployment/link management is intentionally scoped to `~/bin` for portability.
- `.openclaw` and `OpenClaw-workspace` remain local operational repos.
- Canonical docs/planning/scripts now live under `OpenClaw-Ops-Toolkit`.
