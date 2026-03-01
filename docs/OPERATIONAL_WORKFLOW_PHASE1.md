# Operational Workflow (Phase 1)

**Created**: 2026-02-20
**Updated**: 2026-03-01

- [Operational Workflow (Phase 1)](#operational-workflow-phase-1)
  - [Repo Boundary Rules](#repo-boundary-rules)
  - [Context Bootstrapping Flow](#context-bootstrapping-flow)
  - [Script Operations](#script-operations)
  - [Deployment Reference](#deployment-reference)
  - [Commit Cadence](#commit-cadence)
  - [Backup Mode](#backup-mode)
  - [Reporting](#reporting)
  - [Remote Policy](#remote-policy)
  - [Review Cadence](#review-cadence)
  - [Changelog Discipline](#changelog-discipline)

## Repo Boundary Rules

- `.openclaw`: local-only, no remote push.
- `OpenClaw-workspace`: local-only, no remote push.
- `OpenClaw-Ops-Toolkit`: canonical docs/planning/operations repository; only potential remote candidate later.

## Context Bootstrapping Flow

- Stage A always: `SOUL.md`, `USER.md`, `CONTEXTS.md`.
- Stage B route-based:
  - read matched `CONTEXT_INFO.md`
  - read `constraints_file` (`CONTEXT_CONSTRAINTS.md`)
  - continue startup reads listed in context metadata.
- Private route `telegram:group:-1003713298137` is the only route allowed to load `contexts/private/knowledge/*`.

## Script Operations

Canonical scripts live under:

- `~/projects/OpenClaw-Ops-Toolkit/scripts`

Primary operator commands (from `~/bin`):

- Start all: `~/bin/openclaw-stack start all`
- Start llm only: `~/bin/Qwen3 start`
- Start Qwen3.5 llm: `~/bin/Qwen3.5 start`
- Start embedding only: `~/bin/BGEen start`
- Start TTS server: `~/bin/tts start` (or `~/bin/Qwen3TTS start`)
- Start proxy only: `~/bin/proxy start`
- Stop model directly: `~/bin/Qwen3 stop` / `~/bin/Qwen3.5 stop` / `~/bin/BGEen stop`
- Stack status: `~/bin/openclaw-stack status`
- Deploy symlinks: `~/bin/deploy-runtime-links.sh`
- Verify links: `~/bin/verify-runtime-links.sh`
- Runtime report: `~/bin/openclaw-report`
- Sync repo to remote host: `~/bin/sync-ops-scripts`

## Deployment Reference

- See `docs/DEPLOYMENT_SYNC_RUNBOOK.md` for the full sync/deploy/verify flow and remote bash compatibility notes.

## Commit Cadence

- Event-driven commits after meaningful config/policy/workspace changes.
- One lightweight checkpoint commit daily (or at end of active session).
- Use commit tags from `COMMIT_CONVENTIONS.md`.

## Backup Mode

- Time Machine is the baseline backup mechanism.
- No raw runtime/session exports to remote in phase 1.

## Reporting

- Keep generating sanitized reports under:
  - `~/projects/OpenClaw-Ops-Toolkit/docs/reports/YYYY-MM-DD.md`

## Remote Policy

- No push of `.openclaw` or `OpenClaw-workspace` until explicit allowlist + sanitization policy is complete.

## Review Cadence

- Run this mode for one week.
- Reassess remote policy only after one-week churn and restore-readiness review.

## Changelog Discipline

- Add a changelog entry for each meaningful policy/runtime/hygiene/DR change.
- Mark entries as potential blog material only after sanitization review.
