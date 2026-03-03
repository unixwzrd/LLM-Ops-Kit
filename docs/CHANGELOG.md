# Agent Ops Changelog

**Created**: 2026-02-20
**Updated**: 2026-03-01

All notable changes to OpenClaw-Ops-Toolkit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### 2026-03-01 — modelctl verify/test + resilient runtime link flow

- **Scope:** `OpenClaw-Ops-Toolkit/scripts`, `OpenClaw-Ops-Toolkit/docs`
- **Category:** `runtime`, `deployment`, `documentation`
- **What changed:**
  - Added `verify` and `test` actions to `scripts/modelctl` for all model types:
    - `llm`, `embedding`, `tts`
  - `verify` now checks process state and queries `/v1/models` to report model IDs.
  - `test` now runs a type-specific live request:
    - `llm`: `/v1/chat/completions`
    - `embedding`: `/v1/embeddings`
    - `tts`: `/v1/audio/speech` (audio-bytes sanity check)
  - Fixed launcher start-path regression risk by keeping llama launch path explicit for `llm` and `embedding`.
  - Refined runtime-link generation/deploy flow:
    - `generate-manifest` now auto-discovers runtime entry scripts and model launchers.
    - Added TTS wrapper/launcher self-heal support (`scripts/tts`, `scripts/Qwen3TTS`) where needed.
    - `deploy-runtime-links.sh` now fails on missing manifest sources (no silent partial deploy).
    - `sync-ops-scripts.sh` now performs local manifest source precheck and remote manifest regeneration before deploy/verify.
  - Removed `node-hygiene` from managed runtime command surface.
- **Why:**
  - Improve operational confidence: model health checks from one command surface, and deterministic link sync/deploy behavior across hosts.

### 2026-03-01 — Sunday release gate completion (public push prep)

- **Scope:** `OpenClaw-Ops-Toolkit/docs`, `OpenClaw-Ops-Toolkit/scripts`, `OpenClaw-Ops-Toolkit/.gitignore`
- **Category:** `release`, `sanitization`, `validation`
- **What changed:**
  - Enforced internal-doc exclusion for public pushes via `.gitignore` (`docs/internal/`).
  - Kept internal-only documents local while retaining public-safe docs under `docs/`.
  - Sanitized public runbooks to placeholder-first host examples:
    - `docs/PROXY_TAP_RUNBOOK.md`
    - `docs/scripts/proxy.md`
    - `docs/CONFIGURATION.md` (single explicit local-example block retained).
  - Updated and completed `docs/SAFE_PUBLISH_CHECKLIST.md`.
  - Ran release validation gate:
    - `bash -n scripts/*.sh`
    - `python3 -m py_compile scripts/*.py`
    - `scripts/generate-manifest`
    - `scripts/deploy-runtime-links.sh`
    - `scripts/verify-runtime-links.sh`
    - runtime dry checks: `Qwen3/Qwen3.5/BGEen settings`, `proxy status`, `gateway status`
- **Why:**
  - Finalize publish-readiness with no new feature risk and no private/internal leakage in public content.

### 2026-02-28 — Naming cleanup + generic model profile loading

- **Scope:** `OpenClaw-Ops-Toolkit/scripts`, `OpenClaw-Ops-Toolkit/docs`
- **Category:** `maintainability`, `runtime`, `documentation`
- **What changed:**
  - Renamed canonical sync script to `scripts/sync-ops-scripts.sh`.
  - Upgraded `sync-ops-scripts` to run remote link deploy+verify automatically after sync (single-command flow, with `--no-links` escape hatch).
  - Added SSH connection reuse in `sync-ops-scripts` to reduce repeated authentication prompts.
  - Removed deprecated long/duplicate script names:
    - `scripts/generate-runtime-links-manifest.sh`
    - `scripts/sync-OpenClaw-Ops-Toolkit.sh`
    - `scripts/sync-runtime-scripts.sh`
  - Updated docs/runbooks/examples to use `sync-ops-scripts`.
  - Refactored `scripts/modelctl` defaults loading:
    - removed hardcoded model-name routing for defaults,
    - now uses `MODEL_TYPE` from `scripts/models/<Profile>.sh` (`llm` or `embedding`),
    - generic profile usage/help text (`modelctl <model-profile> ...`).
  - Extended `scripts/generate-manifest`:
    - auto-creates launcher symlinks (`scripts/<Profile> -> modelctl`) for all `scripts/models/*.sh`,
    - removes stale modelctl launcher symlinks without matching model profiles.
- **Why:**
  - Make model onboarding drop-in simple and reduce operator error from name-coupled code paths.

### 2026-02-28 — Publish readiness pass (aggressive sanitization, non-breaking defaults)

- **Scope:** `OpenClaw-Ops-Toolkit/scripts`, `OpenClaw-Ops-Toolkit/docs`, `OpenClaw-Ops-Toolkit/.env.example`
- **Category:** `release`, `documentation`, `configuration`, `hygiene`
- **What changed:**
  - Moved internal-only docs from public root to `docs/internal/`:
    - `BACKUP_EXPORT_CONTRACT.md`
    - `SECRETS_AND_AUTH.md`
    - `TODO.md`
  - Added internal release gate checklist:
    - `docs/internal/PUBLISH_EXECUTION_CHECKLIST.md`
  - Added public publish checklist:
    - `docs/SAFE_PUBLISH_CHECKLIST.md`
  - Added environment-driven configuration docs:
    - `.env.example`
    - `docs/CONFIGURATION.md`
  - Added env-fallback support to script defaults while preserving local behavior:
    - `scripts/sync-ops-scripts.sh`
    - `scripts/models/Qwen3.sh`
    - `scripts/models/Qwen3.5.sh`
    - `scripts/proxy`
  - Sanitized publish-facing docs/examples for host/path portability:
    - `README.md`
    - `docs/QUICKSTART.md`
    - `docs/PROXY_TAP_RUNBOOK.md`
    - `docs/scripts/proxy.md`
    - `scripts/openai_proxy_tap.py` usage docstring
- **Why:**
  - Make the repo public-ready without breaking the current working setup.
  - Separate internal planning/security artifacts from public operator docs.
  - Provide explicit override mechanisms for host/path/port configuration.

### 2026-02-26 — Auto-generated runtime link manifest + sync integration

- **Scope:** `OpenClaw-Ops-Toolkit/scripts`, `OpenClaw-Ops-Toolkit/docs`
- **Category:** `automation`, `deployment`, `documentation`
- **What changed:**
  - Added `scripts/generate-manifest` to auto-build `runtime-links.manifest` from launcher symlinks (`scripts/* -> modelctl`) plus static runtime commands.
  - Updated `scripts/sync-ops-scripts.sh` to auto-refresh the manifest before rsync.
  - Added `--no-manifest` flag to `sync-ops-scripts.sh` to skip auto-generation when needed.
  - Updated `docs/ADDING_MODEL_PROFILE.md` to start from defaults/templates first and to use manifest generation workflow.
  - Updated README and deployment runbook language to reflect autogenerated manifest behavior.
- **Why:**
  - Remove manual manifest editing and reduce drift/errors when adding model launchers.

### 2026-02-26 — Documentation expansion for onboarding and operations

- **Scope:** `OpenClaw-Ops-Toolkit/docs`
- **Category:** `documentation`, `operations`, `onboarding`
- **What changed:**
  - Added quickstart, SSH setup, troubleshooting, architecture, glossary, and safe-publish docs:
    - `QUICKSTART.md`
    - `SSH_SETUP_RUNBOOK.md`
    - `TROUBLESHOOTING.md`
    - `ARCHITECTURE.md`
    - `GLOSSARY.md`
    - `SAFE_PUBLISH_CHECKLIST.md`
  - Added per-script mini-manpages under `docs/scripts/` for core runtime commands.
  - Updated `README.md` documentation map to include the new operator guides.
- **Why:**
  - Improve onboarding for less-technical operators while preserving precise references for advanced users.

### 2026-02-26 — Model defaults normalization + manifest-driven runtime links

- **Scope:** `OpenClaw-Ops-Toolkit`
- **Category:** `runtime`, `deployment`, `maintainability`
- **What changed:**
  - Renamed model classification variable from `MODEL_KIND` to `MODEL_TYPE` across launcher/default/model scripts for clearer terminology.
  - Aligned `Qwen3` defaults structure with `Qwen3.5` profile structure:
    - added template mode and sampling preset pattern,
    - normalized grouped sections/comments,
    - fixed template default path to current canonical template file.
  - Added shared runtime link manifest at `scripts/runtime-links.manifest`.
  - Refactored `deploy-runtime-links.sh` and `verify-runtime-links.sh` to consume the same manifest, eliminating duplicate hardcoded link maps.
- **Why:**
  - Reduce drift and breakage risk when adding new launcher commands.
  - Keep model profiles consistent and easier to reason about.
- **Behavior notes:**
  - Runtime link entries are now auto-generated from launcher symlinks via `scripts/generate-manifest` (run automatically by `sync-ops-scripts`).
  - `Qwen3.5` missing-link verification on remote hosts is resolved by re-running deploy after sync.

### 2026-02-26 — Qwen3.5 integration + launcher symlink migration

- **Scope:** `OpenClaw-Ops-Toolkit`, `.openclaw`
- **Category:** `runtime`, `models`, `deployment`
- **What changed:**
  - Added `Qwen3.5` launcher support to `modelctl` (`start|stop|restart|status|settings`) with model-profile resolution.
  - Added `OpenClaw-Ops-Toolkit/scripts/models/Qwen3.5.sh` profile with:
    - stable/new template switching (`QWEN35_TEMPLATE_MODE`),
    - sampling presets (`QWEN35_PRESET=thinking-general|thinking-coding`),
    - env-first override semantics.
  - Added `Qwen3.5` launcher symlink target in runtime link deploy/verify tooling.
  - Standardized launcher policy: use symlinks for command aliases (no hard links) for Git-safe behavior.
  - Added a placeholder Qwen3.5 model entry under `models.providers.llamacpp.models[]` in `openclaw.json`.
- **Why:**
  - Enable side-by-side Qwen3.5 bring-up without destabilizing the current Qwen3 path.
  - Keep launcher alias behavior portable and repository-safe across hosts.
- **Behavior notes:**
  - Placeholder model id must be finalized after first successful `Qwen3.5 start` and runtime model id confirmation.
  - `agents.defaults.model.primary` remains on current Qwen3 model until explicit cutover.

### 2026-02-24 — Context system first-pass finalized (workspace-owned)

- **Scope:** `OpenClaw-workspace`, `OpenClaw-Ops-Toolkit`
- **Category:** `architecture`, `documentation`, `operations`
- **What changed:**
  - Finalized context routing around `OpenClaw-workspace/CONTEXTS.md` as the canonical router/index.
  - Standardized context metadata split:
    - `CONTEXT_INFO.md` for startup/context guide
    - `CONTEXT_CONSTRAINTS.md` for access/tooling/refresh policy
  - Removed `CONVERSATIONS_INDEX.md` from active context path (routing/index now handled by `CONTEXTS.md`).
  - Moved context system docs/templates under workspace ownership:
    - `OpenClaw-workspace/contexts/docs/*`
  - Updated backend docs in `OpenClaw-Ops-Toolkit/docs` to reflect current context architecture and file layout.
- **Why:**
  - Reduce prompt bloat and indirection while making routing deterministic and policy boundaries explicit.
- **Behavior notes:**
  - Private chat route remains bound to `telegram:group:-1003713298137`.
  - Prune-time refresh now maps naturally to context constraints (`refresh_on_prune`, `refresh_files`).

### 2026-02-24 — Documentation normalization for deployment commands

- **Scope:** `OpenClaw-Ops-Toolkit`
- **Category:** `documentation`, `operations`
- **What changed:**
  - Normalized operator docs to the extensionless command surface in `~/bin` (`gateway`, `proxy`, `Qwen3`, `BGEen`, `openclaw-stack`).
  - Updated `docs/OPERATIONAL_WORKFLOW_PHASE1.md` examples to use runtime commands instead of direct script paths.
  - Updated `docs/IMPLEMENTATION_CHECKLIST.md` quick commands and snapshots to match current operator workflow.
  - Corrected `docs/SCRIPT_LAYOUT.md` to the flattened `scripts/` layout (removed stale `scripts/openclaw` reference).
- **Why:**
  - Keep deployment/operator docs aligned with the current runtime surface and reduce drift during remote rollouts.

### 2026-02-24 — Context architecture + private scope migration + script consolidation

- **Scope:** `OpenClaw-workspace`, `OpenClaw-Ops-Toolkit`
- **Category:** `architecture`, `policy`, `operations`, `runtime`
- **What changed:**
  - Implemented channel-keyed context system with deterministic dispatch in `OpenClaw-workspace/CONTEXTS.md`.
  - Added context guide tree under `OpenClaw-workspace/contexts/` for primary and private routes.
  - Migrated private-only relationship files from `memory/*` into `contexts/private/knowledge/*`.
  - Added compatibility stubs at legacy paths to avoid read-path breakage.
  - Updated privacy scope policy to canonical private context paths.
  - Added `CONVERSATIONS_INDEX.md` pointer index for operators.
  - Consolidated startup/utility scripts under `OpenClaw-Ops-Toolkit/scripts/`.
  - Added profile-driven llama startup (`llm`, `embedding`) and stack lifecycle helper.
  - Added symlink-first deployment helper, drift verifier, and fallback sync mode.
  - Updated operational workflow doc and added dedicated context architecture plan doc.
- **Why:**
  - Keep sessions aligned to intended context without manual re-steering.
  - Isolate private knowledge to a single scoped location.
  - Centralize runtime operations in one canonical, versioned script location.
- **Behavior notes:**
  - Runtime path compatibility is preserved via stubs and deploy link tooling.
  - Non-private contexts should no longer load private knowledge by default.
- **Public blog candidate:** yes (context routing + privacy-scoped memory architecture)

### 2026-02-24 — Deployment runbook + portable link strategy

- **Scope:** `OpenClaw-Ops-Toolkit`
- **Category:** `operations`, `deployment`, `portability`
- **What changed:**
  - Added `docs/DEPLOYMENT_SYNC_RUNBOOK.md` with repeatable sync/deploy/verify steps.
  - Standardized runtime link management to `$HOME/bin` only for host portability.
  - Documented remote execution with `/usr/local/bin/bash` for hosts with older default bash.
  - Updated phase workflow doc to reference new runbook and flattened script layout.
- **Why:**
  - Avoid host-specific path failures and make deployment process reusable across macOS/Linux/VPS targets.
- **Public blog candidate:** yes (portable operator workflow + low-friction deployments)

### 2026-02-23 — Jinja tool-loop stabilization + proxy observability hardening

- **Scope:** `OpenClaw-Ops-Toolkit`, `.openclaw`, mounted template at `/Volumes/mps/bin/chatml-tools.jinja`
- **Category:** `runtime`, `prompting`, `observability`, `performance`
- **What changed:**
  - Hardened ChatML Jinja prompt shaping to reduce tool-loop and malformed tool-call failures:
    - Stripped untrusted user metadata wrappers (`Conversation info (untrusted metadata)`) from user content before rendering.
    - Filtered historical assistant reasoning/thinking blocks from replay context.
    - Filtered historical TTS media artifacts (`[[audio_as_voice]]`, `MEDIA:/tmp/openclaw/tts-*`) from tool replay context.
    - Limited replayed tool-role history to recent entries and bounded tool content length (`TOOL_HISTORY_LIMIT`, `TOOL_CONTENT_MAX`).
    - Disabled historical assistant tool-call replay by default (`INCLUDE_TOOL_CALL_HISTORY=false`).
    - Added guard to drop leaked raw tool-call text fragments in assistant history (e.g., partial `{"tool_calls":...}` / `<tool_call>` emissions).
    - Added assistant text sanitization to strip pseudo-tags (`<system>...</system>`) from replay context.
  - Removed force-injected trailing system prompt that explicitly required web_search on each turn, because it was being parroted into user-visible output in some runs.
  - Reworked tool-policy prompt block to be shorter and more deterministic:
    - Active directive: `Make tool calls when needed.`
    - Concise constraints focused on progress/no-repeat/no-blind-retry behavior.
    - Explicit ban on execution-status preambles in final output (e.g., "Executing web_search...").
    - Kept multi-tool chaining allowed when needed for progress.
  - Improved proxy-tap runbook coverage:
    - Validated `jq` parse pattern for mixed NDJSON/plain JSON lines: `(fromjson? // .)`.
    - Added short sample outputs for all documented `tail` + `jq` recipes to improve operator readability.
- **Why:**
  - Repeated incidents of ping-pong loops, malformed/partial tool-call text leakage, stale context replay, and unclear live diagnostics were causing long inference runs and unstable user experience.
- **Performance impact:**
  - Lower context bloat from historical tool/tts/reasoning replay.
  - Fewer runaway retries and lower risk of proxy/request churn.
- **Behavior notes:**
  - Some intermediate streaming artifacts are produced by runtime/message assembly and may still appear transiently before final replacement in Telegram.
  - Final messaging quality improved after removing force-injected web-search tail prompt and compressing tool-policy text.
- **Recovery note:**
  - If behavior regresses, rollback Jinja from latest backup under `/Volumes/mps/bin/chatml-tools.jinja.bak.*` and restart gateway/model.
- **Public blog candidate:** yes (prompt observability + loop hardening case study)

### 2026-02-21 — Prompt transparency + image-context hardening

- **Scope:** `.openclaw`, `OpenClaw-Ops-Toolkit`
- **Category:** `runtime`, `performance`, `observability`
- **What changed:**
  - Added OpenAI proxy tap logging to inspect actual request/response payloads sent to llama.cpp.
  - Added `latest image only` proxy rewrite mode to strip older `image_url` parts from prior turns.
  - Tightened OpenClaw image/context controls: single attachment, newest-first media preference, and stronger context pruning for tool/media-heavy histories.
- **Why:**
  - Prevent stale image replay, repeated tool loops, and context bloat that caused slowdowns/timeouts.
- **Performance impact:**
  - Lower prompt growth under image-heavy chats, improved stability, fewer long-run retries/timeouts.
- **Recovery note:**
  - If stale image errors recur, restart run/session and resend image in a fresh turn; keep proxy `latest image only` enabled.
- **Public blog candidate:** yes (strong case study for cost control + observability-first tuning)

### 2026-02-20 — Privacy-first local repo strategy adopted

- **Scope:** `.openclaw`, `OpenClaw-workspace`, `OpenClaw-Ops-Toolkit`
- **Category:** `policy`, `dr`, `hygiene`
- **What changed:**
  - Adopted local-only mode for `.openclaw` and `OpenClaw-workspace`.
  - Moved canonical hygiene/DR docs to `~/projects/OpenClaw-Ops-Toolkit/docs`.
  - Converted `.openclaw/docs` to pointer docs to avoid drift.
  - Reinforced ignore/untracking of runtime session/auth/device churn files.
- **Why:**
  - Needed rollback capability without exposing sensitive runtime data.
- **Risk/Privacy impact:**
  - Reduced accidental secret/session leakage risk in version control.
- **Recovery note:**
  - Time Machine remains primary backup while DR bundle design is pending.
- **Public blog candidate:** yes (after sanitizing machine-specific details)

### 2026-02-20 — Model config secrets switched to env placeholders

- **Scope:** `.openclaw`
- **Category:** `hygiene`, `runtime`
- **What changed:**
  - Replaced literal API keys in `agents/main/agent/models.json` with `${ENV_VAR}` placeholders.
- **Why:**
  - Prevent accidental disclosure through tracked config files.
- **Risk/Privacy impact:**
  - Lower exposure in repo history; still requires key rotation if previously committed.
- **Recovery note:**
  - Ensure `.env` or Keychain loader provides required vars on restore.
- **Public blog candidate:** yes

### 2026-02-20 — Canonical script/docs consolidation and repo bootstrap

- **Scope:** `.openclaw`, `OpenClaw-Ops-Toolkit`
- **Category:** `hygiene`, `policy`, `dr`
- **What changed:**
  - Confirmed canonical script location at `~/projects/OpenClaw-Ops-Toolkit/scripts/`.
  - Consolidated script ownership to `OpenClaw-Ops-Toolkit` and prepared `.openclaw` for script-directory removal.
  - Initialized `~/projects/OpenClaw-Ops-Toolkit` as a git repository for canonical docs/planning assets.
- **Why:**
  - Reduce repo sprawl and keep policy/history artifacts in one stable project namespace.
- **Risk/Privacy impact:**
  - Improves governance by centralizing non-runtime artifacts.
- **Recovery note:**
  - Canonical docs + scripts are now recoverable from `OpenClaw-Ops-Toolkit` local history.
- **Public blog candidate:** yes (sanitize machine-specific paths)
