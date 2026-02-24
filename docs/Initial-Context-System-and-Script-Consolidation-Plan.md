# Context System + Script Consolidation (Execution-Ready)

## Summary

Implement channel-keyed context bootstrapping in `OpenClaw-workspace`, migrate private context files into `contexts/private` with compatibility stubs, and consolidate operational scripts into `agent-work` with symlink-first deployment plus fallback sync.

## Final Decisions

1. Context layout: `contexts/` + `CONTEXTS.md` index.
2. Bootstrap model: hybrid two-stage load (`SOUL/USER/CONTEXTS` always + context-specific reads).
3. Context keying: channel route key (not sender ID).
4. Private file strategy: move to `contexts/private/` + compatibility stubs.
5. Plan doc target: `agent-work/docs/CONTEXT_ARCHITECTURE_PLAN.md`.
6. Script home: `agent-work/scripts/openclaw`.
7. Deploy mode: symlink-first + drift verifier + secondary sync fallback.

## Implementation Workstream A — Context Architecture

### A1. Create canonical context structure

- Create:
  - `OpenClaw-workspace/contexts/primary/`
  - `OpenClaw-workspace/contexts/private/`
  - `OpenClaw-workspace/contexts/private/knowledge/`
- Add context guides:
  - `OpenClaw-workspace/contexts/primary/telegram_direct.md`
  - `OpenClaw-workspace/contexts/primary/webui.md`
  - `OpenClaw-workspace/contexts/primary/tui.md`
  - `OpenClaw-workspace/contexts/private/telegram_group_-1003713298137.md`
- Add optional indexes:
  - `OpenClaw-workspace/contexts/primary/INDEX.md`
  - `OpenClaw-workspace/contexts/private/INDEX.md`

### A2. Replace `CONTEXTS.md` stub with dispatch map

- Define strict mapping:
  - `telegram:group:-1003713298137` -> private guide
  - `telegram:direct:*` -> primary telegram direct guide
  - `webui:default` -> primary webui guide
  - `tui:default` -> primary tui guide
- Include per-context fields:
  - `context_id`, `match_key`, `purpose`, `startup_reads`, `allowed_paths`, `blocked_paths`, `fallback_behavior`.

### A3. Align `AGENTS.md` startup flow

- Keep your new “Every Session” sequence.
- Add a short note that context-specific file reads are determined by `CONTEXTS.md` route mapping.

## Implementation Workstream B — Private Context Migration

### B1. Move private-only files to context-owned location

Move these to `OpenClaw-workspace/contexts/private/knowledge/`:

- `memory/identity/intimate_rules.md`
- `memory/identity/michael.md`
- `memory/identity/pre_consent_agreement_Mia.md`
- `memory/identity/pre_consent_agreement_Michael.md`
- `memory/personas/mia_and michael_backstory.md`

### B2. Leave compatibility stubs in legacy paths

- Each old file remains as a pointer-only doc to new canonical location.
- No duplicate sensitive body content in legacy files after migration.

### B3. Update privacy policy references

- Update `OpenClaw-workspace/memory/policies/privacy_scope.md` to point to new private canonical paths.
- Keep cross-scope-safe files under `memory/` unchanged.

## Implementation Workstream C — Script Consolidation

### C1. Canonicalize scripts in `agent-work`

- Standardize under `agent-work/scripts/openclaw/`:
  - startup wrappers (gateway/model/embedding/proxy),
  - utility commands (status/stop/restart/report),
  - deploy/sync helpers.

### C2. Merge model/embedding startup logic

- Build shared core script for common llama-server controls.
- Create profile-specific config files:
  - `llm` profile defaults
  - `embedding` profile defaults
- Keep runtime differences in profile files only.

### C3. Deployment mechanics

- Primary: symlink runtime entrypoints from:
  - `~/bin`
  - `/Volumes/mps/bin`
  to canonical `agent-work` scripts.
- Add verifier command to report:
  - missing links,
  - broken links,
  - non-symlink drift.
- Add fallback sync command for environments where symlinks are not practical.

## Implementation Workstream D — Documentation + Changelog

### D1. Add architecture spec

- Create `agent-work/docs/CONTEXT_ARCHITECTURE_PLAN.md` including:
  - routing keys,
  - context file schema,
  - migration matrix old->new,
  - rollout and rollback.

### D2. Update operational docs

- Update `agent-work/docs/OPERATIONAL_WORKFLOW_PHASE1.md` with:
  - context bootstrapping flow,
  - script deploy/verifier commands.

### D3. Update changelog

- Add dated entry in `agent-work/docs/CHANGELOG.md` summarizing:
  - context architecture rollout,
  - private-path migration,
  - script consolidation + deploy verification.

## Validation Matrix

1. Private group bootstrap

- Route: `telegram:group:-1003713298137`
- Expected: private context guide + private knowledge paths loaded.

1. Primary channel bootstrap

- Routes: `telegram:direct:*`, `webui:default`, `tui:default`
- Expected: no private knowledge files loaded.

1. Compatibility paths

- Reading old `memory/identity/*` private files returns pointer stubs.

1. Memory retrieval

- `memorySearch` still returns expected policy/context files from updated layout.

1. Script operations

- Canonical wrappers start/stop/status all services correctly.

1. Deployment integrity

- Verifier passes on both `~/bin` and `/Volumes/mps/bin` targets.

## Assumptions

1. `.openclaw/openclaw.json` already has recursive memory search paths (`memory/**/*.md`) and remains unchanged unless regression found.
2. Channel routing in `.openclaw/openclaw.json` remains authoritative for runtime; context docs define behavior guidance.
3. Sensitive private content must not be duplicated across old and new locations after migration.

## Deliverables

1. Context directory + guides.
2. Replaced `CONTEXTS.md` index map.
3. Migrated private knowledge + compatibility stubs.
4. Consolidated script stack in `agent-work/scripts/openclaw`.
5. Deploy verifier + fallback sync utility.
6. `agent-work/docs/CONTEXT_ARCHITECTURE_PLAN.md`.
7. Changelog + workflow doc updates.
