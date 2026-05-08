# Configuration Guide

Back: [docs/INDEX.md](./INDEX.md)

**Created**: 2026-02-28  
**Updated**: 2026-05-07

- [Configuration Guide](#configuration-guide)
  - [What This Doc Is For](#what-this-doc-is-for)
  - [When to Use This Guide](#when-to-use-this-guide)
  - [Related Docs](#related-docs)
  - [Configuration Rework](#configuration-rework)
  - [Configuration Precedence](#configuration-precedence)
  - [Service-Specific Config Sources](#service-specific-config-sources)
    - [`modelctl`](#modelctl)
    - [`model-proxy`](#model-proxy)
    - [`agentctl`](#agentctl)
    - [`tts-bridge`](#tts-bridge)
  - [Core Environment Variables](#core-environment-variables)
    - [Files and override sources](#files-and-override-sources)
    - [Toolkit roots and paths](#toolkit-roots-and-paths)
    - [Deployment config](#deployment-config)
    - [Hosts and ports](#hosts-and-ports)
    - [Agent runtime](#agent-runtime)
    - [LLM templates and sampling](#llm-templates-and-sampling)
    - [Proxy and tap](#proxy-and-tap)
    - [TTS bridge](#tts-bridge-1)
    - [Secrets](#secrets)
    - [Logs and backups](#logs-and-backups)
  - [Log Marktime](#log-marktime)
  - [Sync Variables](#sync-variables)
  - [Example `.env.local`](#example-envlocal)
  - [Local Example (Examples Only)](#local-example-examples-only)
  - [Remote/Portable Example (Examples Only)](#remoteportable-example-examples-only)
  - [Optional: Secrets Kit Integration](#optional-secrets-kit-integration)
  - [Bootstrapping](#bootstrapping)
  - [Direct-Run Agent Runtime Notes](#direct-run-agent-runtime-notes)
  - [Secrets Kit Runtime Behavior](#secrets-kit-runtime-behavior)
  - [See Also](#see-also)

## What This Doc Is For

This guide is the runtime configuration reference for LLM-Ops-Kit.

Use it to:

- Decide which host/port/path values your scripts should use
- Override defaults without editing scripts
- Configure sync behavior across local and remote hosts
- Move sensitive values to an external secrets manager instead of `.env` files
- Configure staged deployment profiles for local-to-remote or local-to-localhost rollout

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
- Deployment overview: [`DEPLOYMENT_OVERVIEW`](./DEPLOYMENT_OVERVIEW.md)
- Deployment overview: [`DEPLOYMENT_OVERVIEW`](./DEPLOYMENT_OVERVIEW.md)
- Release cleanup: [`RELEASE_AUDIT_CHECKLIST`](./RELEASE_AUDIT_CHECKLIST.md)
- Template env file: [`.env.example`](../.env.example)
- TTS API setup: [`MLX_AUDIO_TTS_GUIDE`](./MLX_AUDIO_TTS_GUIDE.md)

## Configuration Rework

The next configuration system uses JSON as the canonical machine-readable
format and the same platform-neutral directory layout on every OS:

```text
~/.config/llm-ops/        config, inventory, models, agents, profiles
~/.local/share/llm-ops/   bundles, stage data, shared runtime data
~/.local/state/llm-ops/   run state, logs, health, local plan tracking
~/.cache/llm-ops/         GGUF metadata cache and probes
```

Inspect the resolved paths with:

```bash
scripts/llmops-admin config-doctor --dry-run
```

Plan a migration from legacy `~/.llm-ops` env/profile files without writing:

```bash
scripts/llmops-admin migrate-config --dry-run
```

The migration command writes only when run without `--dry-run`, refuses to
overwrite existing JSON unless `--force` is supplied, and treats Secrets Kit as
optional by defaulting the new config to the `env` secrets provider.
When legacy config contains proxy or TTS bridge variables, migration writes
service profiles under `~/.config/llm-ops/services/`.

For llama.cpp/llama-server profiles, the new JSON model profile has a `server`
section for switches that used to be stuffed into raw `EXTRA_FLAGS`, including
cache prompt/reuse, slot save path, speculative ngram settings, `--perf`,
`--fa`, `--no-cpu-moe`, and `--no-host`. The `extra_flags` array remains as an
escape hatch for new llama-server switches before LLM-Ops-Kit has first-class
fields for them.

`modelctl` can already consume JSON model profiles from
`~/.config/llm-ops/models/<profile>.json` by rendering them into the existing
runner environment. This is a transition bridge; the long-term direction is for
runtime commands to use the shared resolver directly.

`agentctl` can consume JSON agent profiles from
`~/.config/llm-ops/agents/<backend>.json` the same way. If a JSON profile exists,
`agentctl` does not auto-seed a legacy per-backend override template; existing
legacy override files still win over JSON values.

`model-proxy` and `tts-bridge` can consume JSON service profiles from
`~/.config/llm-ops/services/model-proxy.json` and
`~/.config/llm-ops/services/tts-bridge.json`. These profiles render into the
same environment variables the wrappers already use.

## Configuration Precedence

The inventory-based admin deployment flow renders host config with this
precedence:

1. global defaults
2. role defaults
3. model defaults
4. profile config
5. host config
6. runtime environment
7. CLI flags

Inspect the effective values and their source with:

```bash
scripts/llmops-admin config-settings --host-name <host-name>
scripts/llmops-admin config-doctor --role llm --model <ModelProfile>
```

The older runtime wrappers still use the script-level precedence below until
the `modelctl` refactor is completed.

Scripts use this precedence (earlier items override later ones):

1. CLI flags (when supported)
2. `~/.llm-ops/config.env` user config for non-secret runtime values
3. `~/.env` and inherited process environment as fallback secret sources
4. `~/.llm-ops/config/<ModelProfile>.env` per-model overrides for model launchers
5. Repo defaults (`scripts/config/hosts.env`)
6. Script defaults

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
- `model-proxy`: CLI flags + environment + JSON service profile
- `agentctl`: CLI flags + environment + JSON agent profiles + per-backend override templates, with backend-native config owned by OpenClaw or Hermes
- `tts-bridge`: CLI flags + environment + JSON service profile + bridge JSON config files

### `modelctl`

Effective precedence:

1. CLI action and any runtime flags passed directly to the launcher
2. exported environment variables
3. `~/.llm-ops/config.env`
4. global defaults under `scripts/defaults/global-defaults.sh`
5. model-type defaults under `scripts/defaults/`
6. shipped model profile under `scripts/models/<ModelProfile>.sh`
7. `~/.llm-ops/config/<ModelProfile>.env`

Notes:

- `modelctl` is the wrapper that owns per-model override files.
- If the current `.env`-style override file is missing, `modelctl` auto-seeds it.
- Legacy `~/.llm-ops/config/<ModelProfile>.sh` files are still loaded and warned about.
- `modelctl` warns when overrides are missing new variables added to shipped profiles.

### `model-proxy`

Effective precedence:

1. CLI flags passed to `model-proxy` / `model-proxy-tap`
2. exported environment variables
3. `~/.llm-ops/config.env`
4. JSON service profile under `~/.config/llm-ops/services/model-proxy.json`
5. built-in wrapper defaults

Notes:

- `model-proxy` can load a JSON service profile, but still renders that profile into the existing wrapper environment.
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
4. existing per-backend override files under `~/.llm-ops/config/agents/`
5. JSON agent profiles under `~/.config/llm-ops/agents/`
6. built-in wrapper defaults
7. backend-native config owned by the selected agent runtime

Notes:

- `agentctl` now seeds optional per-backend override files under `~/.llm-ops/config/agents/`.
- JSON profiles are loaded from `~/.config/llm-ops/agents/openclaw.json` and `~/.config/llm-ops/agents/hermes.json`.
- When a JSON profile exists and no legacy override exists, `agentctl` does not create a legacy override template for that backend.
- Select the default target with `LLMOPS_GATEWAY_BACKEND`:
  - `openclaw` (default)
  - `hermes`
  - `all`
- OpenClaw-specific runtime behavior can be customized in `~/.llm-ops/config/agents/openclaw.env`.
- Hermes-specific wrapper defaults can be customized in `~/.llm-ops/config/agents/hermes.env`.
- Hermes-native runtime behavior is loaded by Hermes from:
  - `~/.hermes/config.yaml`
  - `~/.hermes/.env` (keep placeholder-only; Hermes always reads it)
  - legacy `~/.hermes/gateway.json`
- `LLMOPS_GATEWAY_PORT` only applies to the OpenClaw backend.
- `HERMES_GATEWAY_CMD` overrides the command used to launch Hermes when `backend=hermes`.
- Hermes Secrets Kit use is optional and disabled by default.

### `tts-bridge`

Effective precedence:

1. CLI flags
2. exported environment variables
3. `~/.llm-ops/config.env`
4. JSON service profile under `~/.config/llm-ops/services/tts-bridge.json`
5. files derived from `TTS_BRIDGE_CONFIG_DIR`
6. built-in wrapper defaults

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
- `LLMOPS_RUNTIME_VENV_PATH`: optional runtime Python virtualenv prepended to `PATH` when present.

### Deployment config

- `LLMOPS_DEPLOY_CONFIG`: optional explicit deployment config file override.
- `LLMOPS_DEPLOY_CONFIG_NAME`: internal deployment helper config name. Admin deployments should select hosts through inventory instead.
- Default deploy config path: `./stage/deploy_config/default.env`
- Default local deploy log dir: `./stage/deploy_config/logs/<config-name>`
- Deployment configs are not pushed to remote hosts.
- The staged virtual target filesystem is built under repo-local `stage/<config-name>/` and should remain ignored by git.

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
- `LLMOPS_AGENT_SECKIT_NAMES`: comma-separated names passed to `seckit run` for launchd-managed OpenClaw.
- `HERMES_USE_SECKIT`: optional Hermes-native Secrets Kit toggle (default `0`).
- `HERMES_SECKIT_SERVICE`: `seckit` service namespace for Hermes (default `hermes`).
- `HERMES_SECKIT_ACCOUNT`: `seckit` account namespace for Hermes (default `default`).
- `HERMES_SECKIT_NAMES`: comma-separated secret names for Hermes when that optional path is enabled.
 - `HERMES_SKIP_DOTENV`: skip `~/.hermes/.env` entirely (default `0`).

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

- `LLMOPS_USE_SECKIT`: set to `1` to wrap supported agent launches with `seckit run`.
- `LLMOPS_SECKIT_BIN`: optional `seckit` binary path (default `seckit`).
- `LLMOPS_SECKIT_SERVICE`: `seckit` service namespace (default `openclaw`).
- `LLMOPS_SECKIT_ACCOUNT`: `seckit` account namespace (default `default`).

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

Secrets Kit is a separate tool. LLM-Ops-Kit does not manage, diagnose, import,
or export secrets. When Secrets Kit is installed and explicitly enabled,
LLM-Ops-Kit can launch agent runtimes through `seckit run` so API keys and
tokens are injected into the child process environment by Secrets Kit.

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

# 3) Tell LLM-Ops-Kit to wrap the agent launch with seckit run
cat >> ~/.llm-ops/config.env <<'EOF'
LLMOPS_USE_SECKIT=1
LLMOPS_SECKIT_SERVICE=openclaw
LLMOPS_SECKIT_ACCOUNT=miafour
EOF

# 4) Start the launchd-managed OpenClaw runtime normally
~/bin/agentctl launchd-install openclaw
~/bin/agentctl launchd-status openclaw
```

Notes:

- Keep non-secret host, port, and path settings in `~/.llm-ops/config.env`.
- Keep tokens and API secrets in `seckit`.
- For launchd OpenClaw runs, `agentctl launchd-run openclaw` uses `seckit run --service <service> --account <account> -- ...` only when `LLMOPS_USE_SECKIT=1`.
- If `seckit` is missing for that explicit launch path, startup fails clearly instead of silently pretending secrets were loaded.
- Do not run wrapper startup under `bash -x` / `set -x` when `LLMOPS_USE_SECKIT=1`; shell tracing can expose process environment values.

Current runtime note:

- `seckit` is optional and external. LLM-Ops-Kit does not implement a Secrets Kit doctor, import/export flow, or secret store.

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

## Secrets Kit Runtime Behavior

The supported integration path is process wrapping with `seckit run`. Secrets
Kit remains responsible for storage, diagnostics, import/export, and secure
injection. LLM-Ops-Kit only decides whether a managed runtime should be launched
through that external command.

## See Also

- [Quickstart](./QUICKSTART.md)
- [How It Works](./HOW_IT_WORKS.md)
- [Switching Models and Agents](./SWITCHING.md)
