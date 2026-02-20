# Git Hygiene Policy (Phase 1)

## Purpose
Balance rollback/recovery with privacy/security while agent behavior is still evolving.

## Phase 1 Posture
- `.openclaw`: local-only git mirror (no remote push)
- `OpenClaw-workspace`: local-only git mirror (no remote push)
- `agent-work`: canonical docs/planning repo (only remote candidate later)

## Track in `.openclaw`
- `openclaw.json`
- `agents/*/agent/models.json` (env placeholders only)
- `scripts/**`
- `docs/**` (pointer docs only)

## Do Not Track in `.openclaw`
- auth/runtime/session/device state JSON
- transcript/runtime churn files
- offsets, update state, sqlite runtime db, local backups and .bak artifacts

## Workspace Rule
- Keep workspace versioned locally for rollback.
- No remote push until explicit allowlist policy is finalized.

## Session Rule
- Do not track live runtime transcripts in remote repos.
- If needed, export curated/sanitized session snapshots intentionally.

## Reporting Rule
- Raw logs remain local/ignored.
- Sanitized daily summaries may be stored in:
  - `~/projects/agent-work/docs/reports/YYYY-MM-DD.md`

## Secret Rule
- Config-level secrets: use env placeholders (`${VAR}`) in tracked config files.
- Runtime state files are not env-substitution targets; keep ignored.
