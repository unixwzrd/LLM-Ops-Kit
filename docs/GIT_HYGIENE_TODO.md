# Git Hygiene TODO

**Created**: 2026-02-20
**Updated**: 2026-02-26

## DR Planning (mini-project)

- [ ] Define phase-1 DR restore sequence (clean machine bootstrap).
- [ ] Document required inputs (repos, env vars, local state expectations).
- [ ] Run one dry-run migration checklist and record gaps.

## Session Retention Policy (mini-project)

- [ ] Define curated export format for archival (`markdown` or `json`).
- [ ] Define allowlist rules before any remote archival of conversations.
- [ ] Decide retention period + redaction policy for exports.

## Secret Management Migration (mini-project)

- [ ] Keep `.env` as transitional source of truth for required vars.
- [ ] Add Keychain/Passwords migration plan and loader approach.
- [ ] Rotate any keys previously stored in tracked cleartext files.

## Pre-commit Secret Gate (planned, not now)

- [ ] Define scanner behavior: block raw tokens/keys, allow `${ENV_VAR}` placeholders.
- [ ] Define false-positive suppressions and emergency bypass policy.
- [ ] Add staged rollout checklist (warn-only -> blocking).

## Repo Hygiene Stabilization

- [ ] Reinitialize `~/.openclaw` as clean baseline after one-week churn validation.
- [ ] Review workspace allowlist before any remote push.
- [ ] Keep `agent-work` docs canonical; `.openclaw/docs` should stay pointers only.
