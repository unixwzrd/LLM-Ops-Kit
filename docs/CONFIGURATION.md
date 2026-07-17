# Configuration

Back: [Documentation index](./INDEX.md)

## Authority and Precedence

Configuration precedence is shipped runtime defaults, global JSON, referenced profile JSON, host snapshot values, then temporary CLI overrides. Process environment may provide secrets and documented emergency overrides, but no shell configuration file is read implicitly.

`LLMOPS_CONFIG_HOME`, `LLMOPS_DATA_HOME`, `LLMOPS_STATE_HOME`, and `LLMOPS_CACHE_HOME` select alternate roots. Installed immutable releases use their bundled `current/config` snapshot unless `LLMOPS_CONFIG_HOME` is explicitly set.

Canonical configuration contains:

```text
config.json
inventory.json
models/*.json
agents/*.json
services/*.json
stacks/*.json
```

## Inventory

```json
{
  "schema_version": 1,
  "defaults": {
    "user": "operator",
    "port": 22,
    "install_root": "~/.local/llm-ops",
    "public_bin_dir": "~/.local/bin",
    "ssh_key": "~/.ssh/id_ed25519_llmops"
  },
  "hosts": [
    {
      "name": "model-host",
      "role": "llm",
      "host": "model-host.local",
      "control_host": "model-host.local",
      "transport": "ssh"
    }
  ]
}
```

Supported roles are `admin`, `llm`, `agent`, and `hybrid`. Supported transports are `local` and `ssh`.

`host` is the address used by the deployment authority. `control_host` is the routable address placed in the shared observer catalog for peer-to-peer status checks and defaults to `host`. Set `control_host` explicitly when `host` is `localhost`, a loopback address, or otherwise meaningful only to the deployment authority.

## Components

```json
{
  "id": "chat",
  "host": "model-host",
  "driver": "modelctl",
  "profile": "chat",
  "enabled": false,
  "tags": ["model", "chat"],
  "depends_on": [],
  "ownership": "managed",
  "health": {
    "type": "http",
    "target": "http://127.0.0.1:11434/health",
    "timeout_seconds": 60
  }
}
```

Drivers are `modelctl`, `process`, `launchd`, `model-proxy`, `tts-bridge`, `ssh-tunnel`, `agent`, and gated `command`. Generic process and agent profiles define lifecycle actions as argument arrays. No agent implementation receives privileged treatment.

Tags are optional operator-defined subsystem labels used by `llmops status <tag>`. Libraries embedded inside another process are not independently manageable components unless a process, service, or health adapter is configured for them.

## Reusing Model Profiles

Interactive `llmops init` discovers model profiles under an existing default configuration root when the destination differs. Use `--model-defaults-from <path>` to select another source explicitly.

```bash
llmops init --preset local-lan \
  --model-defaults-from <existing-config-root> \
  --import-model ChatModel \
  --import-model EmbeddingModel \
  --default-chat ChatModel \
  --default-embedding EmbeddingModel
```

Legacy `env` objects are normalized to `environment`. Structured profiles remain structured. Imported model names must be unique, model paths must be absolute, home-relative, or provider references, and model types must be `llm`, `embedding`, or `tts`. Source files are never modified.

Python-backed components select an interpreter explicitly through fields such as `TTS_PYTHON_BIN` or structured `runtime.python_bin`. The value may be an absolute or home-relative interpreter path from Conda, `python -m venv`, virtualenv, or uv, or a simple executable name resolved through the service PATH. An explicit interpreter path is recommended for launchd because it uses the environment's installed packages without sourcing interactive shell profiles. Shell activation is neither required nor performed implicitly.

## Secrets

Never put secret values in tracked JSON. Use `env:<VARIABLE>` or `seckit:<reference>` values. Imported legacy literal secret fields are converted to environment references without copying the literal value.

For current external secret injection, launch the command with required variables already present or set `LLMOPS_ENV_FILE` to an explicit untracked file. LLM-Ops-Kit does not search home, repository, or agent `.env` files.

## Validation

```bash
llmops doctor
llmops doctor --probe
llmops config show --json
llmops component list --json
llmops status --json
llmops plan --action start --json
```

Static validation rejects missing profiles, empty inventory, unknown hosts, dependency cycles, ambiguous references, unsupported drivers, disabled command-driver use, embedded secrets, and known configured port conflicts. Active probing checks connectivity and runtime prerequisites without starting or stopping anything.
