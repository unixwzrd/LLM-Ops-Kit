# Agent Ops Changelog

**Created**: 2026-02-20
**Updated**: 2026-03-31

All notable changes to LLM-Ops-Kit will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### 2026-04-09 — Switching UX, model registration helpers, docs index and cleanup

- **Scope:**
  - Scripts
    - `scripts/agentctl`
    - `scripts/modelctl`
    - `scripts/lib/model_registry.py`
  - Documents
    - `docs/INDEX.md`
    - `docs/HOW_IT_WORKS.md`
    - `docs/SWITCHING.md`
    - `docs/README.md`
    - `docs/QUICKSTART.md`
    - `docs/CONFIGURATION.md`
    - `docs/TROUBLESHOOTING.md`
    - `docs/ARCHITECTURE.md`
    - `docs/ADDING_MODEL_PROFILE.md`
    - `docs/MODELCTL_GUIDE.md`
    - `docs/scripts/agentctl.md`
    - `README.md`
- **Category:** `runtime`, `documentation`
- **What changed:**
  - Added `agentctl switch` and `agentctl current` to simplify swapping OpenClaw/Hermes.
  - Added `modelctl add` with GGUF metadata detection via llama.cpp tools and safe fallback behavior.
  - Moved model registration logic into a dedicated Python helper to keep shell scripts readable.
  - Introduced `docs/INDEX.md`, `HOW_IT_WORKS.md`, and `SWITCHING.md` to make navigation and switching workflows obvious.
  - Reworked configuration documentation to group environment variables by function.

### 2026-03-31 — Unreleased integrated runtime hardening, TTS bridge forwarding, and agentctl surface cleanup

- **Scope:**
  - Scripts
    - `scripts/agentctl`
    - `scripts/gateway`
    - `scripts/openclaw-stack`
    - `scripts/openclaw-report.sh`
    - `scripts/lib/common.sh`
    - `scripts/tts_bridge_server.py`
    - `scripts/model-proxy`
    - `scripts/modelctl`
    - `scripts/precheck`
    - `scripts/runtime-links.manifest`
    - `scripts/tests/test_shell_runtime_helpers.py`
  - Documents
    - `docs/CONFIGURATION.md`
    - `docs/QUICKSTART.md`
    - `docs/DEPLOYMENT_SYNC_RUNBOOK.md`
    - `docs/TROUBLESHOOTING.md`
    - `docs/ARCHITECTURE.md`
    - `docs/scripts/agentctl.md`
    - `docs/scripts/tts-bridge.md`
    - `docs/MLX_AUDIO_TTS_GUIDE.md`
    - `README.md`
- **Category:** `runtime`, `integration`, `security`, `tts`, `documentation`, `testing`
- **What changed:**
  - Formalized fresh-shell runtime precedence so toolkit runtime config comes from `~/.llm-ops/config.env`, `seckit` remains the preferred secret source, and `~/.env`/process env act as fallback secret sources.
  - Added shared runtime tracking for `seckit` export status and environment-secret fallback warnings.
  - `seckit` export failures now remain non-fatal and quiet by default, with `LLMOPS_SECRET_FALLBACK_WARN=0` available to suppress env-secret fallback warnings entirely.
  - Added wrapper-level required-secret declarations so warnings only appear for commands that actually depend on relevant secrets, keeping `tts-bridge` and `model-proxy` quiet when no startup secrets are needed.
  - Added backend-specific agent templates under `scripts/agents/` so `agentctl` can seed per-agent overrides and use an internal `launchd-run` path for backend-native `.env` plus selective `seckit` export.
  - Promoted `agentctl` to the canonical agent runtime surface and moved the implementation there.
  - Removed `gateway` as a supported operator command; it now exits with an error directing operators to `agentctl`.
  - Removed `openclaw-stack` from the supported runtime surface in favor of a clean split: `agentctl` for agents and `modelctl` for models.
  - Renamed wrapper-managed agent runtime state to `agentctl-*` log and pid names for clearer operator output.
  - Updated `openclaw-report` and operator docs to report agents and models separately instead of treating them as a single bundled stack.
  - Added regression coverage for quiet `seckit` failure, explicit environment-secret fallback warning behavior, warning suppression, launchd-oriented env loading, and the renamed `agentctl` wrapper status/log surface.
  - Relaxed `tts-bridge` alias-resolution path validation so `ref_audio` and `ref_text` can point to files that exist only on the upstream MLX host; the bridge now forwards those paths with a warning instead of rejecting the request locally.
  - Updated TTS bridge docs to clarify that voice-map `sample` and optional `ref_text` entries may resolve to upstream/server-side files that are not mounted on the bridge host.
  - `modelctl` now prints the richer post-start status summary for the MLX TTS model path as well, matching the llama profile startup output.
- **Why:**
  - Make cold-start and launchd behavior deterministic, reduce unnecessary `seckit` noise, support server-side-only MLX clone references through the bridge, and simplify the operator surface around a clear agents-versus-models split.

### 2026-03-27 — Release v0.7.5 Model-proxy render mode, chat-template replay hardening, and local precheck tooling

- **Scope:** `LLM-Ops-Kit/scripts/model-proxy`, `LLM-Ops-Kit/scripts/model_proxy_tap.py`, `LLM-Ops-Kit/scripts/precheck`, `LLM-Ops-Kit/scripts/lib/common.sh`, `LLM-Ops-Kit/scripts/modelctl`, `LLM-Ops-Kit/scripts/gateway`, `LLM-Ops-Kit/scripts/tests/test_model_proxy_stats.py`, `LLM-Ops-Kit/docs/scripts/model-proxy.md`, `LLM-Ops-Kit/docs/CONFIGURATION.md`, `LLM-Ops-Kit/README.md`
- **Category:** `proxy`, `prompt-debugging`, `testing`, `documentation`, `shell`
- **What changed:**
  - Added `model-proxy render` as a render-only debugging mode for chat-template investigation.
  - Added `-i`, `--input`, and `--render-input` support for render-only payload input.
  - Added stdin support for render-only mode with `-i -`.
  - Render-only mode now logs raw request text and rendered/template-error output without starting the proxy listener or forwarding upstream.
  - Hardened chat-template rendering by normalizing assistant tool-call payloads for the renderer:
    - when `tool_calls[*].function.arguments` arrives as a JSON string on the wire, it is parsed into a mapping for template rendering only
    - raw request logging remains unchanged
  - Added regression coverage for stringified assistant tool-call arguments in the render path.
  - Added `scripts/precheck` so we can run local shell syntax checks, `shellcheck`, and the Python regression suite before commit/push.
  - Cleaned up shell wrapper issues surfaced by CI `shellcheck`, including:
    - explicit argument passing for runtime-backup pruning helpers
    - safer `llama-server --log-file` launch behavior in `modelctl`
    - removal of unused shell variables
    - a safer log-discovery path in `gateway`
  - Documented the local precheck workflow in the README.
- **Why:**
  - Make prompt/template debugging reproducible from captured request payloads, keep original model templates usable when the OpenAI-style wire payload contains stringified tool-call arguments, and make it easier to catch shell/test regressions locally before pushing.

### 2026-03-26 — Release v0.7.0 Log marktime markers, gateway backend selection, and per-model override cleanup

- **Scope:** `LLM-Ops-Kit/scripts/lib/common.sh`, `LLM-Ops-Kit/scripts/modelctl`, `LLM-Ops-Kit/scripts/tts-bridge`, `LLM-Ops-Kit/scripts/gateway`, `LLM-Ops-Kit/scripts/tests`, `LLM-Ops-Kit/.github/workflows/ci.yml`, `LLM-Ops-Kit/docs/CONFIGURATION.md`, `LLM-Ops-Kit/docs/scripts/gateway.md`, `LLM-Ops-Kit/docs/internal/TODO.md`
- **Category:** `runtime`, `gateway`, `observability`, `configuration`, `testing`, `ci`, `documentation`
- **What changed:**
  - Added shared log marktime support for toolkit-managed service logs.
  - `modelctl` now starts a lightweight marker loop for model server logs and stops it on shutdown/restart.
  - `tts-bridge` now starts the same marker loop for bridge logs and stops it on shutdown/restart.
  - Added new runtime knobs:
    - `LLMOPS_LOG_MARKTIME_ENABLED`
    - `LLMOPS_LOG_MARKTIME_INTERVAL_SECONDS`
    - `LLMOPS_LOG_MARKTIME_FORMAT`
  - Marker lines use a human-readable UTC format such as:
    - `========== Qwen3.5 - MARKTIME  2026-03-26 20:43:28 UTC ==========`
  - `modelctl` now recognizes legacy per-model override files named `~/.llm-ops/config/<Model>.sh` and warns that `~/.llm-ops/config/<Model>.env` is the preferred current convention.
  - `gateway` now supports explicit backend targets via `LLMOPS_GATEWAY_BACKEND` or a command-line target argument, keeping OpenClaw as the default while allowing the same wrapper to launch Hermes with `hermes gateway run`.
  - `gateway` now isolates OpenClaw and Hermes with separate PID/log namespaces so both wrappers can run side by side and be managed independently or together with `all`.
  - Added Hermes-aware `gateway status`, `gateway logs`, and `gateway setup` behavior so the toolkit wrapper can be reused while Hermes continues to own its own `~/.hermes` runtime config.
  - Documented gateway config precedence and clarified that Hermes gateway settings come from Hermes config files rather than the toolkit wrapper.
  - Added regression coverage for:
    - shared log marktime helper behavior
    - per-model override seeding
    - legacy per-model `.sh` override compatibility
  - Added a GitHub Actions workflow that runs shell syntax checks, `shellcheck`, and the Python regression suite on pushes and pull requests.
  - Updated configuration docs to document the marktime settings and the preferred per-model override naming.
  - Added internal backlog notes for future per-model config drift detection and optional append-missing tooling.
- **Why:**
  - Make long-running service logs easier to read and correlate without relying entirely on embedded server timestamps, while keeping per-model override behavior aligned with the current `.env` naming convention.

### 2026-03-25 — Release v0.6.5 TTS bridge status cleanup and upstream-authoritative reporting

- **Scope:** `LLM-Ops-Kit/scripts/tts-bridge`, `LLM-Ops-Kit/scripts/tts_bridge_server.py`, `LLM-Ops-Kit/docs/scripts/tts-bridge.md`
- **Category:** `tts`, `runtime`, `observability`, `documentation`
- **What changed:**
  - Updated `tts-bridge status` to prefer upstream `/v1/models` reporting for the active model instead of blindly echoing the wrapper's local default model path.
  - Removed the misleading `bridge_fallback_model` status line.
  - Updated `tts-bridge status` to read bridge runtime details from the live `/health` payload for:
    - `voice`
    - `config_dir`
    - `pronounce_config`
    - `voice_map_config`
    - `samples_dir`
    - `ref_audio`
    - `ref_text`
  - Simplified bridge startup logging:
    - removed JSON blob startup dumps
    - replaced them with a single note pointing operators to `/health` / `tts-bridge status`
  - Suppressed routine `/health` access-log noise from the bridge so `tts-bridge status` no longer pollutes bridge logs with self-probe entries.
  - Relaxed bridge startup so a missing local `samples_dir` is logged as a warning instead of hard-failing startup, which keeps server-side sample-path deployments working.
  - Detached stdin for the `nohup` launch path in `tts-bridge` to suppress `nohup: ignoring input` noise on normal starts.
- **Why:**
  - Make the bridge report what is actually running upstream, reduce confusing and duplicated status/startup output, and keep bridge logs readable during normal operator workflows.

### 2026-03-22 — Proxy log rotation, response stats, and wrapper hardening

- **Scope:** `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/docs`
- **Category:** `runtime`, `proxy`, `observability`, `tts`, `documentation`
- **What changed:**
  - Added shared time-based log rotation for toolkit-owned Python log writers:
    - new `scripts/log_rotation.py`
    - numbered rollover scheme `active.log` -> `active.log.0.log` -> `active.log.1.log`
    - default rotation period `86400` seconds
    - configurable keep count for rotated files
  - Added log rotation controls to `model-proxy`:
    - `--log-rotate-seconds`
    - `--log-rotate-keep`
    - `MODEL_PROXY_LOG_ROTATE_SECONDS`
    - `MODEL_PROXY_LOG_ROTATE_KEEP`
  - Added log rotation controls to `tts-bridge`:
    - `--log-path`
    - `--log-rotate-seconds`
    - `--log-rotate-keep`
    - `TTS_BRIDGE_LOG_PATH`
    - `TTS_BRIDGE_LOG_ROTATE_SECONDS`
    - `TTS_BRIDGE_LOG_ROTATE_KEEP`
  - Extended `model-proxy` request-end logging with compact llama.cpp/OpenAI-compatible response stats:
    - prompt, completion, total, and cached token counts
    - prompt and generation timing fields
    - finish reasons
  - Hardened the `model-proxy` wrapper startup path:
    - removed the incidental `rg` dependency used for `--upstream` detection
    - load runtime env before validating upstream settings
    - support `MODEL_PROXY_CHAT_TEMPLATE` as a config/env default
  - Added focused tests for:
    - rotating log writer behavior
    - proxy response-stats extraction
  - Updated operator docs and runbooks with:
    - rotation settings
    - live `jq` examples for token and timing stats
- **Why:**
  - Keep proxy and bridge logs bounded during long-running sessions, improve live observability for llama.cpp performance and token usage, and remove brittle wrapper startup behavior that depended on shell environment quirks.

### 2026-03-20 — Qwen3TTS base-model default path correction

- **Scope:** `LLM-Ops-Kit/scripts/models/Qwen3TTS.sh`
- **Category:** `tts`, `runtime`
- **What changed:**
  - Changed the default canonical `Qwen3TTS` model path from the `CustomVoice` build to the `Base` build:
    - `Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit` -> `Qwen3-TTS-12Hz-0.6B-Base-8bit`
- **Why:**
  - Keep the launcher default aligned with the base speech model, while voice-clone behavior is handled by the bridge and explicit reference inputs instead of assuming a clone-tuned model path.

### 2026-03-19 — Config-driven TTS pronunciation and voice mapping

- **Scope:** `LLM-Ops-Kit/scripts/tts_bridge_server.py`, `LLM-Ops-Kit/scripts/tts-bridge`, `LLM-Ops-Kit/docs`, `LLM-Ops-Kit/examples/tts`
- **Category:** `tts`, `runtime`, `configuration`, `documentation`
- **What changed:**
  - Added config-driven pronunciation substitution to `tts-bridge`:
    - `pronounce.json` support under `~/.llm-ops`
    - longest-match replacement for symbol and text fragments before requests are forwarded upstream
  - Added config-driven voice alias mapping:
    - `voice-map.json` support under `~/.llm-ops`
    - friendly voice names can resolve to clone sample audio and matching transcript files
    - explicit incoming `ref_audio` and `ref_text` continue to override alias-derived values
  - Added bridge config path controls:
    - `--config-dir`
    - `--pronounce-config`
    - `--voice-map-config`
    - `--samples-dir`
    - matching environment variables for each
  - Hardened bridge validation and diagnostics:
    - invalid JSON fails loudly at startup
    - malformed alias entries fail loudly
    - missing alias-resolved sample or transcript files fail clearly at request time
    - `/health` now reports resolved config paths and entry counts
  - Added example configs:
    - `examples/tts/pronounce.example.json`
    - `examples/tts/voice-map.example.json`
  - Added focused bridge tests covering config resolution, substitution behavior, alias resolution, and failure paths.
- **Why:**
  - Make clone-voice selection and pronunciation cleanup operator-configurable without editing code, and give the bridge clearer failure modes when local TTS inputs are incomplete or invalid.

### 2026-03-16 — BGEm3 embedding profile rollout

- **Scope:** `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/docs`, `LLM-Ops-Kit/README.md`
- **Category:** `runtime`, `embedding`, `documentation`
- **What changed:**
  - Added a first-class `BGEm3` launcher and model profile for `bge-m3-Q8_0-GGUF/bge-m3-q8_0.gguf`.
  - Switched `openclaw-stack` embedding operations to `BGEm3`.
  - Updated runtime-facing status/report names from `bge-small-en` to `bge-m3`.
  - Added `BGEm3` to runtime link management so installs deploy the new launcher into `~/bin`.
  - Updated operator docs to prefer `BGEm3` as the embedding command surface.
- **Why:**
  - Keep the runtime naming aligned with the actual embedding model and avoid future installs drifting back to the old `bge-small-en` profile.

### 2026-03-13 — Direct-run gateway stabilization and runtime rollback clarity

- **Scope:** `LLM-Ops-Kit/scripts/gateway`, `LLM-Ops-Kit/scripts/install-runtime.sh`, `LLM-Ops-Kit/scripts/lib/common.sh`, `LLM-Ops-Kit/docs/QUICKSTART.md`, `LLM-Ops-Kit/docs/CONFIGURATION.md`, `LLM-Ops-Kit/docs/internal/TODO.md`
- **Category:** `runtime`, `gateway`, `secrets`, `documentation`
- **What changed:**
  - Kept `gateway` on the direct-run wrapper path using `openclaw gateway run --port ...` under `nohup` instead of the standard service-only `openclaw gateway start` flow.
  - Updated `gateway status` to report:
    - direct-run wrapper mode
    - wrapper log paths under `~/.llm-ops/logs`
    - current OpenClaw app log path under `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
    - a note that `openclaw logs --follow` may still fail in this mode
  - Added `gateway logs` to tail:
    - `~/.llm-ops/logs/gateway.log`
    - `~/.llm-ops/logs/gateway.err.log`
    - `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
    as the reliable local follow path during this stabilization phase.
  - Removed install-time `seckit` loading from `install-runtime`, keeping installs independent from runtime secret injection.
  - Kept the `common.sh` env ordering and xtrace fixes that allow placeholder-style env files and safer `seckit` export handling.
  - Documented the current stabilization baseline:
    - runtime `Secrets-Kit` disabled (`LLMOPS_USE_SECKIT=0`)
    - direct-run gateway as the current source of truth
    - standard service/LaunchAgent path and CLI RPC follow/probe behavior deferred for a later return pass
- **Why:**
  - Preserve a working OpenClaw runtime on the primary operator machine while isolating the LaunchAgent/service path and CLI RPC issues as separate follow-up work.

### 2026-03-10 — Optional Secrets Kit runtime loading

- **Scope:** `LLM-Ops-Kit/scripts/lib/common.sh`, `LLM-Ops-Kit/docs/CONFIGURATION.md`, `LLM-Ops-Kit/docs/QUICKSTART.md`
- **Category:** `security`, `configuration`, `runtime`
- **What changed:**
  - Added optional `seckit` integration at the shared runtime env-loader layer.
  - New supported knobs:
    - `LLMOPS_USE_SECKIT=1`
    - `LLMOPS_SECKIT_BIN`
    - `LLMOPS_SECKIT_SERVICE`
    - `LLMOPS_SECKIT_ACCOUNT`
  - When enabled, wrappers now import secret values from `seckit export --format shell --service ... --account ... --all` during startup.
  - Documented the supported flow for keeping API secrets in `seckit` while leaving non-secret host, port, and path values in `~/.llm-ops/config.env`.
- **Why:**
  - Make `Secrets Kit` usable across `gateway`, `model-proxy`, and `tts-bridge` without requiring manual `eval` in the caller shell.
  - Keep secret management optional and runtime-scoped instead of forcing a new prerequisite.

### 2026-03-10 — TTS bridge client-disconnect handling

- **Scope:** `LLM-Ops-Kit/scripts/tts_bridge_server.py`
- **Category:** `tts`, `runtime`, `stability`
- **What changed:**
  - Hardened `tts-bridge` response handling for client disconnects during `/v1/audio/speech`
  - Treats `BrokenPipeError` and `ConnectionResetError` as normal disconnects instead of trying to emit a second fallback response
  - Reduces noisy traceback spam when OpenClaw abandons an in-flight TTS request and closes the socket early
- **Why:**
  - Keep bridge logs focused on real upstream failures instead of secondary disconnect noise from already-closed client connections.

### 2026-03-10 — Install flow and docs cleanup

- **Scope:** `LLM-Ops-Kit/README.md`, `LLM-Ops-Kit/docs/QUICKSTART.md`, `LLM-Ops-Kit/docs/scripts/install-runtime.md`, `LLM-Ops-Kit/docs/internal/`, `LLM-Ops-Kit/scripts/runtime-links.manifest`
- **Category:** `documentation`, `installation`, `hygiene`
- **What changed:**
  - Clarified the first-time install path so public docs now start from:
    - `git clone`
    - `cd` into the repo
    - `./scripts/install-runtime --source "$PWD"`
  - Corrected the runtime layout description so docs and manifest language match the real installed-runtime behavior under `~/.llm-ops/current` with links in `~/bin`.
  - Added explicit Python helper dependency guidance for `jinja2`.
  - Kept `mlx-audio` called out as a separate requirement for the MLX TTS path.
  - Trimmed public docs by moving planning/layout material under `docs/internal/`.
- **Why:**
  - Make the public install story match the way the toolkit is actually deployed and used.
  - Reduce confusion around runtime layout, Python helper requirements, and what belongs in public docs versus internal operator notes.

### 2026-03-09 — Installed-runtime default + CustomVoice bridge fix + retention controls

- **Scope:** `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/docs`, `LLM-Ops-Kit/README.md`, `LLM-Ops-Kit/CHANGELOG.md`
- **Category:** `runtime`, `tts`, `deployment`, `maintenance`, `documentation`
- **What changed:**
  - Fixed `tts-bridge` compatibility for `mlx_audio` `CustomVoice` models:
    - detect `CustomVoice` from the effective model id
    - keep forwarding `model`, `voice`, `ref_audio`, and `ref_text`
    - use server-side clone reference paths in the validated deployment flow
    - keep normalizing unsupported formats such as `opus` and `ogg` to `wav`
  - Expanded bridge observability:
    - `/health` reports effective defaults and compatibility fallbacks
    - `tts-bridge status` now prints runtime mode, runtime root, and retention policy
  - Validated end-to-end `CustomVoice` cloning against the upstream `mlx-audio` fix that:
    - resolves `ref_text` from a server-side path
    - prefers the ICL clone path when clone refs are present
    - is currently available in `unixwzrd/mlx-audio` until upstream PR `#558` merges
  - Decoupled runtime asset resolution from the source checkout:
    - `LLMOPS_ROOT` now resolves to the actual runtime root, not `scripts/`
    - `Qwen3` and `Qwen3.5` templates now resolve from the runtime root
    - `model-proxy` now resolves `model-proxy-tap` from the runtime root
    - `modelctl settings` now prints `RUNTIME_MODE` and `RUNTIME_ROOT`
  - Removed more silent repo-coupled behavior:
    - installed runtime remains the default normal operating mode
    - `sync-ops-scripts` now defaults to `installed` mode unless repo mode is explicitly requested
    - link deployment and verification now use `RUNTIME_DIR` semantics instead of assuming a checkout path
  - Added built-in log rotation and backup pruning:
    - shared retention helpers in `scripts/lib/common.sh`
    - wrappers now rotate/prune known logs on startup
    - install flow now prunes old runtime backups under `~/.llm-ops/backups`
    - new `runtime-maintenance` command provides `status|rotate|prune|run`
  - Updated docs and top-level README to describe:
    - installed-runtime-first operation
    - `CustomVoice` bridge requirements
    - retention settings and maintenance command
- **Why:**
  - Keep the bridge/OpenClaw TTS path stable while validating the final working `CustomVoice` clone flow against the upstream `mlx-audio` fix.
  - Make the installed runtime self-contained so removing or moving the source checkout does not break normal operations.
  - Prevent silent disk growth from logs and install backups.

### 2026-03-06 — Runtime ownership boundary + rename finalization + status hardening

- **Scope:** `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/docs`, `LLM-Ops-Kit/.env.example`, `LLM-Ops-Kit/CHANGELOG.md`
- **Category:** `runtime`, `deployment`, `configuration`, `documentation`
- **What changed:**
  - Finalized project naming/path defaults to `LLM-Ops-Kit` in scripts and docs.
  - Moved changelog to project root (`CHANGELOG.md`) and updated references.
  - Fixed `sync-ops-scripts` host loading so shared env defaults apply before host assignment.
  - Added repo-local/default host source support and documented host precedence.
  - Added deploy-time symlink auto-heal for rename migration:
    - heals managed links from `~/projects/OpenClaw-Ops-Toolkit/...` to `~/projects/LLM-Ops-Kit/...`
    - preserves conflict behavior for non-symlink collisions.
  - Hardened `modelctl status`:
    - persistent state file per model process (`$LLMOPS_RUN_DIR/<pid_name>.state`)
    - PID command validation via `ps`
    - fast API responsiveness probe to `/v1/models`
    - state cleanup on stop.
  - Moved toolkit-owned runtime defaults from `.openclaw` to `.llm-ops`:
    - `LLMOPS_RUN_DIR` default -> `~/.llm-ops/run`
    - `LLMOPS_LOG_DIR` default -> `~/.llm-ops/logs`
    - config loading now prefers `~/.llm-ops/config.env`
    - removed implicit dependence on `~/.openclaw/.env` for toolkit scripts.
  - Updated proxy and runbook defaults to `.llm-ops` paths.
  - Updated `.env.example` to include `LLMOPS_HOME`, `LLMOPS_RUN_DIR`, and `LLMOPS_LOG_DIR`.
- **Why:**
  - Keep ownership boundaries clear: OpenClaw controls `.openclaw`, toolkit controls `.llm-ops`.
  - Improve operator reliability during host/network changes and repo-path migration.
  - Make status output more trustworthy than pidfile-only checks.

### 2026-03-03 — TTS bridge wiring + sync path normalization + prompt replay pruning

- **Scope:** `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/docs`
- **Category:** `runtime`, `tts`, `deployment`, `prompting`, `documentation`
- **What changed:**
  - Added OpenAI-compatible local TTS bridge:
    - `scripts/openai_tts_bridge.py`
    - `scripts/tts-bridge`
  - Added managed runtime command entry for `tts-bridge` in `scripts/runtime-links.manifest`.
  - Added script guide for bridge operations:
    - `docs/scripts/tts-bridge.md`
    - linked from `docs/scripts/README.md`
  - Extended MLX TTS runbook with OpenClaw bridge wiring:
    - `OPENAI_TTS_BASE_URL=http://127.0.0.1:11440/v1`
    - Added known `mlx-audio` packaging gaps and required extra installs (`uvicorn`, `webrtcvad`, `fastapi`, `python-multipart`).
  - Hardened `sync-ops-scripts.sh` remote path normalization to handle literal `~` path artifacts.
  - Reduced template replay pressure for tool messages in Qwen3.5 templates to avoid context bloat:
    - stricter tool history limit
    - shorter tool payload truncation ceiling
- **Why:**
  - Keep OpenClaw TTS provider surface stable while supporting MLX CustomVoice payload requirements.
  - Prevent sync path drift on mixed local/remote tilde usage.
  - Improve long-session stability under heavy tool-use history.

### 2026-03-01 — modelctl verify/test + resilient runtime link flow

- **Scope:** `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/docs`
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

- **Scope:** `LLM-Ops-Kit/docs`, `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/.gitignore`
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
    - `python -m py_compile scripts/*.py`
    - `scripts/generate-manifest`
    - `scripts/deploy-runtime-links.sh`
    - `scripts/verify-runtime-links.sh`
    - runtime dry checks: `Qwen3/Qwen3.5/BGEm3 settings`, `proxy status`, `gateway status`
- **Why:**
  - Finalize publish-readiness with no new feature risk and no private/internal leakage in public content.

### 2026-02-28 — Naming cleanup + generic model profile loading

- **Scope:** `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/docs`
- **Category:** `maintainability`, `runtime`, `documentation`
- **What changed:**
  - Renamed canonical sync script to `scripts/sync-ops-scripts.sh`.
  - Upgraded `sync-ops-scripts` to run remote link deploy+verify automatically after sync (single-command flow, with `--no-links` escape hatch).
  - Added SSH connection reuse in `sync-ops-scripts` to reduce repeated authentication prompts.
  - Removed deprecated long/duplicate script names:
    - `scripts/generate-runtime-links-manifest.sh`
    - `scripts/sync-LLM-Ops-Kit.sh`
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

- **Scope:** `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/docs`, `LLM-Ops-Kit/.env.example`
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

- **Scope:** `LLM-Ops-Kit/scripts`, `LLM-Ops-Kit/docs`
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

- **Scope:** `LLM-Ops-Kit/docs`
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

- **Scope:** `LLM-Ops-Kit`
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

- **Scope:** `LLM-Ops-Kit`, `.openclaw`
- **Category:** `runtime`, `models`, `deployment`
- **What changed:**
  - Added `Qwen3.5` launcher support to `modelctl` (`start|stop|restart|status|settings`) with model-profile resolution.
  - Added `LLM-Ops-Kit/scripts/models/Qwen3.5.sh` profile with:
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

- **Scope:** `OpenClaw-workspace`, `LLM-Ops-Kit`
- **Category:** `architecture`, `documentation`, `operations`
- **What changed:**
  - Finalized context routing around `OpenClaw-workspace/CONTEXTS.md` as the canonical router/index.
  - Standardized context metadata split:
    - `CONTEXT_INFO.md` for startup/context guide
    - `CONTEXT_CONSTRAINTS.md` for access/tooling/refresh policy
  - Removed `CONVERSATIONS_INDEX.md` from active context path (routing/index now handled by `CONTEXTS.md`).
  - Moved context system docs/templates under workspace ownership:
    - `OpenClaw-workspace/contexts/docs/*`
  - Updated backend docs in `LLM-Ops-Kit/docs` to reflect current context architecture and file layout.
- **Why:**
  - Reduce prompt bloat and indirection while making routing deterministic and policy boundaries explicit.
- **Behavior notes:**
  - Private chat route remains bound to `telegram:group:-1003713298137`.
  - Prune-time refresh now maps naturally to context constraints (`refresh_on_prune`, `refresh_files`).

### 2026-02-24 — Documentation normalization for deployment commands

- **Scope:** `LLM-Ops-Kit`
- **Category:** `documentation`, `operations`
- **What changed:**
  - Normalized operator docs to the extensionless command surface in `~/bin` (`gateway`, `proxy`, `Qwen3`, `BGEm3`, `openclaw-stack`).
  - Updated `docs/OPERATIONAL_WORKFLOW_PHASE1.md` examples to use runtime commands instead of direct script paths.
  - Updated `docs/IMPLEMENTATION_CHECKLIST.md` quick commands and snapshots to match current operator workflow.
  - Corrected `docs/SCRIPT_LAYOUT.md` to the flattened `scripts/` layout (removed stale `scripts/openclaw` reference).
- **Why:**
  - Keep deployment/operator docs aligned with the current runtime surface and reduce drift during remote rollouts.

### 2026-02-24 — Context architecture + private scope migration + script consolidation

- **Scope:** `OpenClaw-workspace`, `LLM-Ops-Kit`
- **Category:** `architecture`, `policy`, `operations`, `runtime`
- **What changed:**
  - Implemented channel-keyed context system with deterministic dispatch in `OpenClaw-workspace/CONTEXTS.md`.
  - Added context guide tree under `OpenClaw-workspace/contexts/` for primary and private routes.
  - Migrated private-only relationship files from `memory/*` into `contexts/private/knowledge/*`.
  - Added compatibility stubs at legacy paths to avoid read-path breakage.
  - Updated privacy scope policy to canonical private context paths.
  - Added `CONVERSATIONS_INDEX.md` pointer index for operators.
  - Consolidated startup/utility scripts under `LLM-Ops-Kit/scripts/`.
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

- **Scope:** `LLM-Ops-Kit`
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

- **Scope:** `LLM-Ops-Kit`, `.openclaw`, mounted template at `/Volumes/mps/bin/chatml-tools.jinja`
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

- **Scope:** `.openclaw`, `LLM-Ops-Kit`
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

- **Scope:** `.openclaw`, `OpenClaw-workspace`, `LLM-Ops-Kit`
- **Category:** `policy`, `dr`, `hygiene`
- **What changed:**
  - Adopted local-only mode for `.openclaw` and `OpenClaw-workspace`.
  - Moved canonical hygiene/DR docs to `~/projects/LLM-Ops-Kit/docs`.
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

- **Scope:** `.openclaw`, `LLM-Ops-Kit`
- **Category:** `hygiene`, `policy`, `dr`
- **What changed:**
  - Confirmed canonical script location at `~/projects/LLM-Ops-Kit/scripts/`.
  - Consolidated script ownership to `LLM-Ops-Kit` and prepared `.openclaw` for script-directory removal.
  - Initialized `~/projects/LLM-Ops-Kit` as a git repository for canonical docs/planning assets.
- **Why:**
  - Reduce repo sprawl and keep policy/history artifacts in one stable project namespace.
- **Risk/Privacy impact:**
  - Improves governance by centralizing non-runtime artifacts.
- **Recovery note:**
  - Canonical docs + scripts are now recoverable from `LLM-Ops-Kit` local history.
- **Public blog candidate:** yes (sanitize machine-specific paths)
