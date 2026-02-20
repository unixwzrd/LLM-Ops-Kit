# TODO

## DR Planning (mini-project)
- [ ] Define phase-1 restore sequence for a clean machine.
- [ ] List required inputs: local repos, env vars, identity setup, service startup order.
- [ ] Validate a dry-run migration checklist and record failures.

## Session Retention Policy (mini-project)
- [ ] Define curated export format (`markdown` or `json`) for archival.
- [ ] Define allowlist/redaction rules before any remote archival.
- [ ] Define retention windows and deletion policy.

## Secret Management Migration (mini-project)
- [ ] Keep `.env` transitional for required runtime vars.
- [ ] Define Keychain/Passwords migration and env loader strategy.
- [ ] Rotate any keys previously exposed in tracked files/history.

## Pre-commit Secret Gate (planned, not implemented)
- [ ] Define detection rules: block raw keys/tokens, allow `${ENV_VAR}` placeholders.
- [ ] Define suppression, override, and audit process.
- [ ] Plan staged rollout: warn-only -> blocking.

## Repo Hygiene Stabilization
- [ ] Keep `.openclaw` and `OpenClaw-workspace` local-only through phase 1.
- [ ] Reinitialize `.openclaw` as clean baseline after one-week churn validation.
- [ ] Keep canonical policy/TODO docs in `agent-work/docs`; pointer docs in `.openclaw/docs`.

## Accounts and Integrations
- [ ] Finish GitHub setup for Mia account (`gh auth login` + scoped repo access).
- [ ] Configure Google Workspace auth for `gog`.
- [ ] Configure iCloud CalDAV app-specific password for Mia.

## Documentation Discipline
- [ ] Maintain Agent Ops Changelog in `docs/CHANGELOG.md` for recovery history and blog-ready notes.
