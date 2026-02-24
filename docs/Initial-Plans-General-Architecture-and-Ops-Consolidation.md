# Context Architecture + Ops Consolidation Plan

## Summary

Build a channel-keyed context system that bootstraps each chat correctly, migrate private/intimate context content into dedicated context-owned files (with compatibility stubs), and consolidate startup/utility scripts under `agent-work` with symlink-based deployment verification. Document everything in a new architecture plan plus changelog updates.

## Scope

1. Context architecture in `OpenClaw-workspace`.
2. Private context migration and compatibility layer.
3. Startup/utility script consolidation in `agent-work`.
4. Documentation and changelog coverage for reproducibility/blogging.

## Target Artifacts

1. `OpenClaw-workspace/CONTEXTS.md` (index + dispatch rules).
2. `OpenClaw-workspace/contexts/` (new canonical context directory).
3. `OpenClaw-workspace/contexts/private/` (private chat context package).
4. `OpenClaw-workspace/memory/identity/*` and `OpenClaw-workspace/memory/personas/*` compatibility stubs (for moved private files).
5. `agent-work/docs/CONTEXT_ARCHITECTURE_PLAN.md` (canonical implementation spec).
6. `agent-work/docs/CHANGELOG.md` update for this migration.
7. `agent-work/scripts/openclaw/` canonical script home + deploy verifier.
8. `~/bin` and `/Volumes/mps/bin` symlinks targeting canonical scripts.

## Public Interfaces / Config Contracts

1. **Context key format** (primary selector): `channel:mode:target`.
2. Supported keys in phase 1:
   - `telegram:group:-1003713298137` (private/intimate chat).
   - `telegram:direct:*` (primary direct Telegram).
   - `webui:default` (primary control chat).
   - `tui:default` (primary control chat).
3. `CONTEXTS.md` contract fields per context:
   - `context_id`
   - `match_key`
   - `purpose`
   - `startup_reads`
   - `allowed_memory_paths`
   - `blocked_memory_paths`
   - `response_style`
   - `tooling_expectations`
   - `fallback_behavior`
4. Compatibility stubs contract:
   - Old path remains readable.
   - Old file contains pointer-only content to new canonical path.
   - No private content duplication across old/new once migration completes.

## Implementation Design

### 1) Context Index and Dispatch

1. Replace `OpenClaw-workspace/CONTEXTS.md` stub with a strict index that maps `match_key` to context guide files under `OpenClaw-workspace/contexts/`.
2. Define one context guide per channel role.
3. Use two-stage bootstrap:
   - Stage A always: `SOUL.md`, `USER.md`, `CONTEXTS.md`.
   - Stage B context-specific: files listed in `startup_reads` for matched context.

### 2) Context Directory Structure

1. Create `OpenClaw-workspace/contexts/primary/` for control chat contexts.
2. Create `OpenClaw-workspace/contexts/private/` for intimate/private chat.
3. Create context guide files:
   - `OpenClaw-workspace/contexts/primary/telegram_direct.md`
   - `OpenClaw-workspace/contexts/primary/webui.md`
   - `OpenClaw-workspace/contexts/primary/tui.md`
   - `OpenClaw-workspace/contexts/private/telegram_group_-1003713298137.md`
4. Create optional context-local indexes:
   - `OpenClaw-workspace/contexts/private/INDEX.md`
   - `OpenClaw-workspace/contexts/primary/INDEX.md`

### 3) Private Context Migration

1. Move private-only files to `OpenClaw-workspace/contexts/private/knowledge/`:
   - `memory/identity/intimate_rules.md`
   - `memory/identity/michael.md`
   - `memory/identity/pre_consent_agreement_Mia.md`
   - `memory/identity/pre_consent_agreement_Michael.md`
   - `memory/personas/mia_and michael_backstory.md`
2. Leave compatibility stubs at old paths pointing to new files.
3. Update `OpenClaw-workspace/memory/policies/privacy_scope.md` to reference new canonical private paths.
4. Keep cross-scope safe files in `memory/` unchanged (`MEMORY.md`, non-sensitive identity files, dated logs).

### 4) Startup / Utility Script Consolidation

1. Set canonical script home to `agent-work/scripts/openclaw/`.
2. Refactor startup scripts into shared + profile model:
   - Shared core: common env/bootstrap/logging/process handling.
   - Profile files for `llm` and `embedding` defaults.
3. Consolidate entrypoints:
   - OpenClaw gateway startup wrapper.
   - llama-server startup wrapper (profile-driven: llm/embedding).
   - proxy tap startup wrapper.
   - status/stop/restart/report wrappers.
4. Add deploy verifier script that checks:
   - Required symlinks exist in `~/bin` and `/Volumes/mps/bin`.
   - Symlink targets resolve to canonical scripts.
   - Drift report if any path is copy/file instead of symlink.

### 5) Documentation and Change Management

1. Create `agent-work/docs/CONTEXT_ARCHITECTURE_PLAN.md` with:
   - context schema
   - migration map (old path -> new path)
   - rollout sequence
   - rollback instructions
2. Update `agent-work/docs/CHANGELOG.md` with a dated entry covering:
   - context architecture introduction
   - private context migration
   - script consolidation and symlink verification
3. Add short operator section to `agent-work/docs/OPERATIONAL_WORKFLOW_PHASE1.md` linking to new context architecture doc and deploy verifier usage.

## Rollout Plan

1. Phase 1: Author docs/spec first in `agent-work/docs`.
2. Phase 2: Build context files/index in `OpenClaw-workspace`.
3. Phase 3: Migrate private files + write compatibility stubs.
4. Phase 4: Consolidate scripts and establish symlinks.
5. Phase 5: Validate with controlled test cycle.
6. Phase 6: Changelog + operational docs finalization.

## Test Cases and Validation

1. **Context dispatch**
   - Input: Telegram group `-1003713298137`.
   - Expectation: private context guide selected; private startup reads executed.
2. **Cross-channel isolation**
   - Input: Telegram direct chat.
   - Expectation: private-only files not loaded; primary context guide used.
3. **Compatibility reads**
   - Input: old private file paths.
   - Expectation: pointer/stub resolves human/operator intent and does not break workflows.
4. **Memory search coverage**
   - Input: query for `privacy_scope` and private-policy terms.
   - Expectation: results include intended files under new context path and safe memory files.
5. **Script orchestration**
   - Start all services from canonical wrappers.
   - Expectation: gateway/model/embedding/proxy start cleanly with per-service logs.
6. **Symlink integrity**
   - Run deploy verifier.
   - Expectation: no drift and all runtime paths resolve to canonical scripts.
7. **Regression checks**
   - Private chat should avoid generic “assistant-only” repetition and correctly load private context.
   - No unwanted leakage of private context in direct/web/tui channels.

## Assumptions and Defaults

1. Canonical scripts live in `agent-work/scripts/openclaw`.
2. Context selection key is channel-route-based, not sender-id-based.
3. Two-stage bootstrap is used globally.
4. Private files are migrated to `contexts/private/` with compatibility stubs at legacy locations.
5. `CONTEXT_ARCHITECTURE_PLAN.md` is the canonical implementation spec document.
6. `memorySearch.extraPaths` remains recursive for markdown discovery (already set to `memory/**/*.md` in `.openclaw/openclaw.json`).

## Acceptance Criteria

1. New chat sessions self-bootstrap correctly by channel context without manual prompting.
2. Private context behavior works in `telegram:group:-1003713298137` and stays isolated elsewhere.
3. Startup and utility scripts are managed from one canonical location with validated symlink deployment.
4. Documentation is complete enough for reproducible rollout and public write-up.
