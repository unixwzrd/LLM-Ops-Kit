# Configuration Guide

Back: [docs/INDEX.md](./INDEX.md)

**Created**: 2026-02-28  
**Updated**: 2026-03-27

- [Configuration Guide](#configuration-guide)
  - [What This Doc Is For](#what-this-doc-is-for)
  - [When to Use This Guide](#when-to-use-this-guide)
  - [Related Docs](#related-docs)
  - [Configuration Precedence](#configuration-precedence)
  - [Core Environment Variables](#core-environment-variables)
  - [Sync Variables](#sync-variables)
  - [Example `.env.local`](#example-envlocal)
  - [Local Example (Current Operator Setup)](#local-example-current-operator-setup)
  - [Remote/Portable Example](#remoteportable-example)
  - [Optional: Secrets Kit Integration](#optional-secrets-kit-integration)
  - [Bootstrapping](#bootstrapping)

## What This Doc Is For

This guide is the runtime configuration reference for LLM-Ops-Kit.

Use it to:

- Decide which host/port/path values your scripts should use
- Override defaults without editing scripts
- Configure sync behavior across local and remote hosts
- Move sensitive values to an external secrets manager instead of `.env` files

If you are only trying to start services quickly, use [QUICKSTART](./QUICKSTART.md) first.

## When to Use This Guide

Use this file when you are:

- Setting up a new machine or VM
- Changing upstream LLM/TTS host or ports
- Migrating repo paths
- Standardizing settings before publishing docs/scripts

## Related Docs

- Main index: [`README`](../README.md)
- Quickstart: [`QUICKSTART`](./QUICKSTART.md)
- Sync/deploy workflow: [`DEPLOYMENT_SYNC_RUNBOOK`](./DEPLOYMENT_SYNC_RUNBOOK.md)
- Template env file: [`.env.example`](../.env.example)
- TTS API setup: [`MLX_AUDIO_TTS_GUIDE`](./MLX_AUDIO_TTS_GUIDE.md)

## Configuration Precedence

Scripts use this precedence (earlier items override later ones):

1. CLI flags (when supported)
2. `~/.llm-ops/config.env` user config for non-secret runtime values
3. `seckit` exports when `LLMOPS_USE_SECKIT=1`
4. `~/.env` and inherited process environment as fallback secret sources
5. `~/.llm-ops/config/<ModelProfile>.env` per-model overrides for model launchers
6. Repo defaults (`scripts/config/hosts.env`)
7. Script defaults

Note:
- Toolkit scripts do not rely on `~/.openclaw/.env` by default.
- Keep toolkit configuration in `~/.llm-ops/config.env`, but keep it minimal if you want per-model overrides to drive behavior.
- Keep runtime routing config in `~/.llm-ops/config.env`, not in `~/.env`.
- Reserve `~/.env` for secret fallback values only.
- For model-specific overrides, prefer `~/.llm-ops/config/<ModelProfile>.env`.
- If a per-model override file is missing, `modelctl` auto-seeds it from the shipped model profile the first time that launcher is used and prints a notice.
- Legacy per-model override files named `~/.llm-ops/config/<ModelProfile>.sh` are still detected and loaded, but `~/.llm-ops/config/<ModelProfile>.env` is now the preferred convention.

## Service-Specific Config Sources

Not every wrapper uses the same kind of config input. The most useful mental
model is:

- `modelctl`: global env + per-model override file + shipped model profile
- `model-proxy`: CLI flags + environment only
- `agentctl`: CLI flags + environment + per-backend override templates, with backend-native config owned by OpenClaw or Hermes
- `tts-bridge`: CLI flags + environment + bridge JSON config files

### `modelctl`

Effective precedence:

1. CLI action and any runtime flags passed directly to the launcher
2. exported environment variables
3. `~/.llm-ops/config.env`
4. `~/.llm-ops/config/<ModelProfile>.env`
5. shipped model profile under `scripts/models/<ModelProfile>.sh`
6. model-type defaults under `scripts/defaults/`

Notes:

- `modelctl` is the wrapper that owns per-model override files.
- If the current `.env`-style override file is missing, `modelctl` auto-seeds it.
- Legacy `~/.llm-ops/config/<ModelProfile>.sh` files are still loaded and warned about.

### `model-proxy`

Effective precedence:

1. CLI flags passed to `model-proxy` / `model-proxy-tap`
2. exported environment variables
3. `~/.llm-ops/config.env`
4. built-in wrapper defaults

Notes:

- `model-proxy` does not have its own dedicated config file.
- It does persist live runtime metadata under `~/.llm-ops/run/model-proxy-live-*`,
  but those files are for status/reporting, not configuration input.
- `model-proxy render` is a render-only debugging path that reuses the normal
  env/CLI config surface and does not require upstream connectivity.
- The most important config inputs are:
  - `LLMOPS_UPSTREAM_HOST`
  - `LLMOPS_UPSTREAM_PORT`
  - `MODEL_PROXY_LISTEN_HOST`
  - `MODEL_PROXY_LISTEN_PORT`
  - `MODEL_PROXY_CHAT_TEMPLATE`

### `agentctl`

Effective precedence:

1. CLI action
2. exported environment variables
3. `~/.llm-ops/config.env`
4. built-in wrapper defaults
5. backend-native config owned by the selected agent runtime

Notes:

- `agentctl` now seeds optional per-backend override files under `~/.llm-ops/config/agents/`.
- Select the default target with `LLMOPS_GATEWAY_BACKEND`:
  - `openclaw` (default)
  - `hermes`
  - `all`
- OpenClaw-specific runtime behavior can be customized in `~/.llm-ops/config/agents/openclaw.env`.
- Hermes-specific wrapper defaults can be customized in `~/.llm-ops/config/agents/hermes.env`.
- Hermes-native runtime behavior is loaded by Hermes from:
  - `~/.hermes/config.yaml`
  - `~/.hermes/.env`
  - legacy `~/.hermes/gateway.json`
- `LLMOPS_GATEWAY_PORT` only applies to the OpenClaw backend.
- `HERMES_GATEWAY_CMD` overrides the command used to launch Hermes when `backend=hermes`.

### `tts-bridge`

Effective precedence:

1. CLI flags
2. exported environment variables
3. `~/.llm-ops/config.env`
4. files derived from `TTS_BRIDGE_CONFIG_DIR`
5. built-in wrapper defaults

Notes:

- `tts-bridge` does not use a single dedicated shell config file of its own.
- Its extra structured config comes from JSON files, typically:
  - `~/.llm-ops/pronounce.json`
  - `~/.llm-ops/voice-map.json`
- Environment chooses the paths; the JSON files provide the structured bridge data.

## Core Environment Variables

### Files and override sources

- `~/.llm-ops/config.env`: global toolkit config (keep minimal if you prefer per-model overrides).
- `~/.llm-ops/config/<ModelProfile>.env`: per-model overrides loaded by `modelctl`.
- `scripts/config/hosts.env`: repo-owned default host/IP config for wrappers.
- `~/.llm-ops/config/agents/openclaw.env`: per-backend OpenClaw overrides seeded by `agentctl`.
- `~/.llm-ops/config/agents/hermes.env`: per-backend Hermes overrides seeded by `agentctl`.

### Toolkit roots and paths

- `LLMOPS_HOME`: toolkit state root (default `~/.llm-ops`).
- `LLMOPS_RUN_DIR`: runtime pid/state dir (default `$LLMOPS_HOME/run`).
- `LLMOPS_LOG_DIR`: toolkit log dir (default `$LLMOPS_HOME/logs`).
- `LLMOPS_ROOT`: canonical runtime asset root for the installed payload.

### Hosts and ports

- `LLMOPS_UPSTREAM_HOST`: default upstream model host for wrappers.
- `LLMOPS_UPSTREAM_PORT`: default upstream model port for wrappers.
- `LLMOPS_SYNC_HOST`: optional dedicated sync host override (falls back to `LLMOPS_UPSTREAM_HOST`).
- `MODEL_PROXY_LISTEN_HOST`: bind host for `model-proxy`.
- `MODEL_PROXY_LISTEN_PORT`: bind port for `model-proxy`.

### Agent runtime

- `LLMOPS_GATEWAY_BACKEND`: `agentctl` backend selector (`openclaw` default).
- `LLMOPS_GATEWAY_PORT`: OpenClaw direct-run port used by `agentctl`.
- `HERMES_GATEWAY_CMD`: Hermes command path/name used by `agentctl`.
- `LLMOPS_AGENT_NATIVE_ENV_FILE`: backend-native `.env` file path for launchd runs.
- `LLMOPS_AGENT_SECKIT_NAMES`: comma-separated `seckit` names to export for a backend.
- `LLMOPS_SKIP_SECKIT_LOAD`: internal flag used to defer `seckit` loading until backend config is known.

### LLM templates and sampling

- `USE_CUSTOM_TEMPLATE`: set to `1` to enable a llama.cpp custom chat template.
- `CHAT_TEMPLATE`: explicit template path when `USE_CUSTOM_TEMPLATE=1`.
- `TEMP`, `TOP_P`, `TOP_K`, `MIN_P`, `PRESENCE_PENALTY`, `REPEAT_PENALTY`: sampling overrides.
- `CACHE_TYPE_K`, `CACHE_TYPE_V`: KV cache data types for llama.cpp (for example `q8_0`).

### Proxy and tap

- `MODEL_PROXY_TAP_BIN`: explicit path to `model-proxy-tap`.
- `MODEL_PROXY_LOG_ROTATE_SECONDS`: rotation period in seconds (default `86400`).
- `MODEL_PROXY_LOG_ROTATE_KEEP`: number of rotated proxy logs to keep (default `5`).

### TTS bridge

- `OPENAI_TTS_BASE_URL`: OpenClaw OpenAI-TTS provider base URL (for example `http://127.0.0.1:11440/v1`).
- `TTS_BRIDGE_HOST`: bind host for `tts-bridge`.
- `TTS_BRIDGE_PORT`: bind port for `tts-bridge`.
- `TTS_BRIDGE_UPSTREAM_BASE`: upstream MLX Audio base URL.
- `TTS_BRIDGE_MODEL`: default model path injected by bridge.
- `TTS_BRIDGE_VOICE`: default voice injected by bridge.
- `TTS_BRIDGE_REF_AUDIO`: default reference audio file.
- `TTS_BRIDGE_REF_TEXT`: default reference transcript file (or literal text).
- `TTS_BRIDGE_PYTHON_BIN`: python binary used by the bridge launcher.

### Secrets

- `LLMOPS_USE_SECKIT`: set to `1` to load secrets from `seckit`.
- `LLMOPS_SECKIT_BIN`: optional `seckit` binary path (default `seckit`).
- `LLMOPS_SECKIT_SERVICE`: `seckit` service namespace (default `openclaw`).
- `LLMOPS_SECKIT_ACCOUNT`: `seckit` account namespace (default `default`).
- `LLMOPS_SECRET_FALLBACK_WARN`: set to `0` to suppress env fallback warnings.

### Logs and backups

- `LLMOPS_LOG_ROTATE_BYTES`: rotate logs after this many bytes.
- `LLMOPS_LOG_ROTATE_KEEP`: number of rotated logs to keep per active log.
- `LLMOPS_LOG_ROTATE_MAX_AGE_DAYS`: optional max age for rotated logs.
- `LLMOPS_BACKUP_KEEP`: number of runtime install backups to keep.
- `LLMOPS_BACKUP_MAX_AGE_DAYS`: optional max age for runtime install backups.

## Log Marktime

Toolkit-managed service logs can emit periodic human-readable timestamp markers
to make long-running log review easier.

- `LLMOPS_LOG_MARKTIME_ENABLED`: enable periodic log markers (`1` by default).
- `LLMOPS_LOG_MARKTIME_INTERVAL_SECONDS`: marker interval in seconds (`300` by default).
- `LLMOPS_LOG_MARKTIME_FORMAT`: `date` format string used for the timestamp body
  (default: `+%Y-%m-%d %H:%M:%S UTC`).

Current marker shape:

```text
========== <label> - MARKTIME  YYYY-MM-DD hh:mm:ss UTC ==========
```

## Sync Variables

- `SYNC_HOST`
- `SYNC_USER`
- `SYNC_REMOTE_DIR`
- `SYNC_LOCAL_DIR`
- `SYNC_KEY_PATH`
- `SYNC_KEY_TTL`

## Example `.env.local`

```bash
# Copy from .env.example and adapt values.
LLMOPS_UPSTREAM_HOST=<upstream-host>
LLMOPS_UPSTREAM_PORT=<upstream-port>
MODEL_PROXY_LISTEN_HOST=127.0.0.1
MODEL_PROXY_LISTEN_PORT=<listen-port>
LLMOPS_HOME=~/.llm-ops
LLMOPS_RUN_DIR=~/.llm-ops/run
LLMOPS_LOG_DIR=~/.llm-ops/logs
LLMOPS_LOG_ROTATE_BYTES=10485760
LLMOPS_LOG_ROTATE_KEEP=5
LLMOPS_BACKUP_KEEP=5

SYNC_HOST=<sync-host>
SYNC_USER=<your-user>
SYNC_REMOTE_DIR=~/projects/LLM-Ops-Kit
SYNC_LOCAL_DIR=~/projects/LLM-Ops-Kit/
```

## Local Example (Examples Only)

```bash
export LLMOPS_UPSTREAM_HOST="<example-upstream-host>"
export LLMOPS_UPSTREAM_PORT="11434"
export MODEL_PROXY_LISTEN_HOST="127.0.0.1"
export MODEL_PROXY_LISTEN_PORT="11434"
```

## Remote/Portable Example (Examples Only)

```bash
export LLMOPS_UPSTREAM_HOST="<upstream-host>"
export LLMOPS_UPSTREAM_PORT="<upstream-port>"
export MODEL_PROXY_LISTEN_HOST="127.0.0.1"
export MODEL_PROXY_LISTEN_PORT="<listen-port>"
```

## Optional: Secrets Kit Integration

If you do not want sensitive values in `.env` files, use `seckit` and let the shared LLM-Ops-Kit runtime loader import those values during startup.

Project:

- `seckit` from `Secrets-Kit`
- Example URL: `https://github.com/unixwzrd/Secrets-Kit`

Example flow:

```bash
# 1) Install (example from GitHub)
python -m pip install "git+https://github.com/unixwzrd/Secrets-Kit.git"

# 2) Store secret values
echo 'sk-example' | seckit set --name OPENAI_API_KEY --stdin --kind api_key --service openclaw --account miafour
echo 'el-example' | seckit set --name ELEVENLABS_API_KEY --stdin --kind api_key --service openclaw --account miafour

# 3) Tell LLM-Ops-Kit to load them during startup
cat >> ~/.llm-ops/config.env <<'EOF'
LLMOPS_USE_SECKIT=1
LLMOPS_SECKIT_SERVICE=openclaw
LLMOPS_SECKIT_ACCOUNT=miafour
EOF

# 4) Start runtimes normally
~/bin/agentctl restart
~/bin/modelctl status
```

Notes:

- Keep non-secret host, port, and path settings in `~/.llm-ops/config.env`.
- Keep tokens and API secrets in `seckit`.
- When enabled, the shared runtime loader imports `seckit` exports before `agentctl`, `model-proxy`, `tts-bridge`, and related wrappers start.
- If `seckit` is missing or export fails, wrappers log a warning and continue without imported secrets.
- Do not run wrapper startup under `bash -x` / `set -x` when `LLMOPS_USE_SECKIT=1`; shell tracing can expose exported secrets.

Current runtime note:

- `Secrets-Kit` integration is intentionally disabled for live OpenClaw startup on the primary operator machine while the agent runtime path is being stabilized.
- The current operational setting is `LLMOPS_USE_SECKIT=0`.
- `seckit` remains installed for manual use, migration, export, and future re-integration.

## Bootstrapping

Use [`.env.example`](../.env.example) as a starting template for your local environment values.

Recommended user-owned config path:

```bash
mkdir -p ~/.llm-ops
cat > ~/.llm-ops/config.env <<'EOF'
LLMOPS_UPSTREAM_HOST=<example-upstream-host>
LLMOPS_SYNC_HOST=<example-upstream-host>
LLMOPS_UPSTREAM_PORT=11434
MODEL_PROXY_LISTEN_HOST=127.0.0.1
MODEL_PROXY_LISTEN_PORT=11434
LLMOPS_HOME=$HOME/.llm-ops
LLMOPS_RUN_DIR=$HOME/.llm-ops/run
LLMOPS_LOG_DIR=$HOME/.llm-ops/logs
LLMOPS_LOG_ROTATE_BYTES=10485760
LLMOPS_LOG_ROTATE_KEEP=5
LLMOPS_BACKUP_KEEP=5
USE_CUSTOM_TEMPLATE=1
CHAT_TEMPLATE=$HOME/.llm-ops/current/scripts/templates/Qwen3.5-chatml-tools.jinja
EOF
```

Example per-model override:

```bash
mkdir -p ~/.llm-ops/config
cat > ~/.llm-ops/config/Qwen3.5.env <<'EOF'
USE_CUSTOM_TEMPLATE=1
CHAT_TEMPLATE=$HOME/.llm-ops/current/scripts/templates/Qwen3.5-chatml-no-tools.jinja
TEMP=0.9
TOP_P=0.95
TOP_K=20
MIN_P=0.0
PRESENCE_PENALTY=1.5
REPEAT_PENALTY=1.0
EOF
```

## Direct-Run Agent Runtime Notes

The current known-good startup path on the primary operator machine is the direct-run `agentctl` wrapper:

- `agentctl start` launches the OpenClaw agent runtime under `nohup`
- wrapper logs go to `~/.llm-ops/logs/agentctl-openclaw.log` and `~/.llm-ops/logs/agentctl-openclaw.err.log`
- OpenClaw app logs go to `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
- `agentctl logs` tails all three of those files together

At the moment, the standard OpenClaw service path is considered deferred work:

- the native OpenClaw service entrypoint expects an installed LaunchAgent on macOS
- `openclaw logs --follow` and related native health/probe commands may still fail against a live direct-run agent runtime because the CLI RPC attach path is not stable yet in this environment

## Secrets Kit Fallback Behavior

When `LLMOPS_USE_SECKIT=1`, wrappers try `seckit` first for secrets. If export succeeds, those values are used with no warning. If export fails, wrappers continue with environment-based secret fallback instead of aborting.

Warnings are only emitted when both of these are true:

- the current wrapper declares relevant secret names
- one or more of those secrets is actually present in environment fallback

This keeps commands like `tts-bridge status` quiet when they do not need secrets at all, while still warning when a command is running on env-backed secrets instead of `seckit`.

## See Also

- [Quickstart](./QUICKSTART.md)
- [How It Works](./HOW_IT_WORKS.md)
- [Switching Models and Agents](./SWITCHING.md)
