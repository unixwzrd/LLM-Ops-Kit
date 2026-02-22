# Agent Ops Changelog

**Created**: 2026-02-20
**Updated**: 2026-02-21

All notable changes to agent-work will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

