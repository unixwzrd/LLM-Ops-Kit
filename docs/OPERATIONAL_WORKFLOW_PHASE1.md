# Operational Workflow (Phase 1)

## Repo Boundary Rules
- `.openclaw`: local-only, no remote push.
- `OpenClaw-workspace`: local-only, no remote push.
- `agent-work`: canonical docs/planning repository; only potential remote candidate later.

## Commit Cadence
- Event-driven commits after meaningful config/policy/workspace changes.
- One lightweight checkpoint commit daily (or at end of active session).
- Use commit tags from `COMMIT_CONVENTIONS.md`.

## Backup Mode
- Time Machine is the baseline backup mechanism.
- No raw runtime/session exports to remote in phase 1.

## Reporting
- Keep generating sanitized reports under:
  - `~/projects/agent-work/docs/reports/YYYY-MM-DD.md`

## Remote Policy
- No push of `.openclaw` or `OpenClaw-workspace` until explicit allowlist + sanitization policy is complete.

## Review Cadence
- Run this mode for one week.
- Reassess remote policy only after one-week churn and restore-readiness review.

## Changelog Discipline
- Add a changelog entry for each meaningful policy/runtime/hygiene/DR change.
- Mark entries as potential blog material only after sanitization review.
