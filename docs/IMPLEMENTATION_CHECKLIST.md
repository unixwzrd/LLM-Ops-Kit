# Implementation Checklist

**Created**: 2026-02-24
**Updated**: 2026-02-26


Use this checklist to control change scope and avoid drift while refactoring context + runtime scripts.

## Phase 0 - Freeze Window

- [x] Pause new structural edits until checklist is in place.
- [ ] Confirm active services state snapshot taken.
- [ ] Confirm git status captured for all repos.
- [ ] Confirm rollback points identified.

### Snapshot Commands

```bash
git -C ~/OpenClaw-workspace status --short
git -C ~/projects/agent-work status --short
git -C ~/.openclaw status --short
~/bin/openclaw-stack status
```

## Phase 1 - Context Architecture (Workspace)

- [x] `CONTEXTS.md` is canonical router/index.
- [x] Route-matched contexts use `CONTEXT_INFO.md`.
- [x] Per-context policy/guardrails split to `CONTEXT_CONSTRAINTS.md`.
- [x] `AGENTS.md` startup flow aligned with route-based context load.
- [x] `privacy_scope.md` updated to canonical private paths.
- [x] Removed redundant `CONVERSATIONS_INDEX.md` from active model path.

### Validation Gate A

- [ ] Validate route key presence:
  - `telegram:group:-1003713298137`
  - `telegram:direct:*`
  - `webui:default`
  - `tui:default`
- [ ] Validate private path references only point to `contexts/private/knowledge/*`.
- [ ] Validate each active context has both `CONTEXT_INFO.md` and `CONTEXT_CONSTRAINTS.md`.

## Phase 2 - Private Memory Migration

- [x] Private files moved to `contexts/private/knowledge/*`.
- [x] Compatibility stubs left at legacy `memory/*` paths.
- [ ] Verify no sensitive duplication remains in legacy files.

### Validation Gate B

- [ ] Open each legacy stub and confirm pointer-only content.
- [ ] Open each canonical private file and confirm full content present.

## Phase 3 - Runtime Script Consolidation (agent-work)

- [x] Stack supports parallel startup where safe (models can start in parallel).
- [x] Components are independently startable/stoppable (no mandatory coupled startup/shutdown).
- [x] Canonical script home is `scripts/`.
- [x] Unified extensionless launcher (`modelctl`) implemented.
- [x] Model defaults mapped by launcher name:
  - `models/Qwen3.sh`
  - `models/BGEen.sh`
- [x] Generic defaults split:
  - `defaults/llm-defaults.sh`
  - `defaults/embedding-defaults.sh`
- [x] Start aliases created:
  - `~/bin/Qwen3`
  - `~/bin/BGEen`
- [x] Action-based wrappers in place:
  - `~/bin/gateway [start|stop|restart|status]`
  - `~/bin/proxy [start|stop|restart|status]`
  - `~/bin/openclaw-stack [start|stop|restart|status] [all|gateway|llm|embedding|proxy|models]`
- [x] Jinja copied to canonical location:
  - `scripts/templates/chatml-tools.jinja`

### Validation Gate C

- [ ] Shell syntax check passes for all scripts.
- [ ] `~/bin/openclaw-stack` target control works (`all|gateway|llm|embedding|proxy|models`).
- [ ] `~/bin/Qwen3 start` starts llm profile.
- [ ] `~/bin/BGEen start` starts embedding profile.

## Phase 4 - Deployment and Link Integrity

- [x] Symlink-first deployment executed.
- [x] Link verifier executed successfully.
- [ ] Fallback sync mode dry-run reviewed.

### Validation Gate D

- [ ] Verify expected links in `~/bin`.
- [ ] Verify expected links in `$HOME/bin` on target host(s).
- [ ] Confirm no non-symlink drift for managed targets.

## Phase 5 - Documentation and Changelog

- [x] `CONTEXT_ARCHITECTURE_PLAN.md` updated for v1 context split (`CONTEXT_INFO` + `CONTEXT_CONSTRAINTS`).
- [x] `OPERATIONAL_WORKFLOW_PHASE1.md` updated.
- [x] `CHANGELOG.md` updated with 2026-02-24 context pass entries.

## Rollback Checklist

- [ ] If startup fails, run `~/bin/openclaw-stack stop`.
- [ ] Repoint links via `~/bin/deploy-runtime-links.sh`.
- [ ] Restore prior script files from git history if needed.
- [ ] Restart only affected components; llm/embedding/proxy can be managed independently.

## Operator Commands (Quick)

```bash
# Stack control
~/bin/openclaw-stack start
~/bin/openclaw-stack status
~/bin/openclaw-stack stop

# Model-specific control
~/bin/Qwen3 start
~/bin/BGEen start
~/bin/Qwen3 stop
~/bin/BGEen stop

# Deploy integrity
~/bin/deploy-runtime-links.sh
~/bin/verify-runtime-links.sh
```
