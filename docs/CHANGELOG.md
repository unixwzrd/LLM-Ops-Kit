# Agent Ops Changelog

**Created**: 2026-02-20
**Updated**: 2026-02-24

All notable changes to agent-work will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

