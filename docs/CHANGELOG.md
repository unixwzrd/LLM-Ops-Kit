# Agent Ops Changelog

**Created**: 2026-02-20
**Updated**: 2026-02-24

All notable changes to agent-work will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### 2026-02-24 — Context system first-pass finalized (workspace-owned)

- **Scope:** `OpenClaw-workspace`, `agent-work`
- **Category:** `architecture`, `documentation`, `operations`
- **What changed:**
  - Finalized context routing around `OpenClaw-workspace/CONTEXTS.md` as the canonical router/index.
  - Standardized context metadata split:
    - `CONTEXT_INFO.md` for startup/context guide
    - `CONTEXT_CONSTRAINTS.md` for access/tooling/refresh policy
  - Removed `CONVERSATIONS_INDEX.md` from active context path (routing/index now handled by `CONTEXTS.md`).
  - Moved context system docs/templates under workspace ownership:
    - `OpenClaw-workspace/contexts/docs/*`
  - Updated backend docs in `agent-work/docs` to reflect current context architecture and file layout.
- **Why:**
  - Reduce prompt bloat and indirection while making routing deterministic and policy boundaries explicit.
- **Behavior notes:**
  - Private chat route remains bound to `telegram:group:-1003713298137`.
  - Prune-time refresh now maps naturally to context constraints (`refresh_on_prune`, `refresh_files`).

### 2026-02-24 — Documentation normalization for deployment commands

- **Scope:** `agent-work`
- **Category:** `documentation`, `operations`
- **What changed:**
  - Normalized operator docs to the extensionless command surface in `~/bin` (`gateway`, `proxy`, `Qwen3`, `BGEen`, `openclaw-stack`).
  - Updated `docs/OPERATIONAL_WORKFLOW_PHASE1.md` examples to use runtime commands instead of direct script paths.
  - Updated `docs/IMPLEMENTATION_CHECKLIST.md` quick commands and snapshots to match current operator workflow.
  - Corrected `docs/SCRIPT_LAYOUT.md` to the flattened `scripts/` layout (removed stale `scripts/openclaw` reference).
- **Why:**
  - Keep deployment/operator docs aligned with the current runtime surface and reduce drift during remote rollouts.

### 2026-02-24 — Context architecture + private scope migration + script consolidation

- **Scope:** `OpenClaw-workspace`, `agent-work`
- **Category:** `architecture`, `policy`, `operations`, `runtime`
- **What changed:**
  - Implemented channel-keyed context system with deterministic dispatch in `OpenClaw-workspace/CONTEXTS.md`.
  - Added context guide tree under `OpenClaw-workspace/contexts/` for primary and private routes.
  - Migrated private-only relationship files from `memory/*` into `contexts/private/knowledge/*`.
  - Added compatibility stubs at legacy paths to avoid read-path breakage.
  - Updated privacy scope policy to canonical private context paths.
  - Added `CONVERSATIONS_INDEX.md` pointer index for operators.
  - Consolidated startup/utility scripts under `agent-work/scripts/openclaw`.
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

- **Scope:** `agent-work`
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

- **Scope:** `agent-work`, `.openclaw`, mounted template at `/Volumes/mps/bin/chatml-tools.jinja`
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

- **Scope:** `.openclaw`, `agent-work`
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

- **Scope:** `.openclaw`, `OpenClaw-workspace`, `agent-work`
- **Category:** `policy`, `dr`, `hygiene`
- **What changed:**
  - Adopted local-only mode for `.openclaw` and `OpenClaw-workspace`.
  - Moved canonical hygiene/DR docs to `~/projects/agent-work/docs`.
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

- **Scope:** `.openclaw`, `agent-work`
- **Category:** `hygiene`, `policy`, `dr`
- **What changed:**
  - Confirmed canonical script location at `~/projects/agent-work/scripts/openclaw`.
  - Consolidated script ownership to `agent-work` and prepared `.openclaw` for script-directory removal.
  - Initialized `~/projects/agent-work` as a git repository for canonical docs/planning assets.
- **Why:**
  - Reduce repo sprawl and keep policy/history artifacts in one stable project namespace.
- **Risk/Privacy impact:**
  - Improves governance by centralizing non-runtime artifacts.
- **Recovery note:**
  - Canonical docs + scripts are now recoverable from `agent-work` local history.
- **Public blog candidate:** yes (sanitize machine-specific paths)

