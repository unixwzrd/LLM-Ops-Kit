# Configuration

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

## Authority and Precedence

Configuration precedence is shipped runtime defaults, global JSON, referenced profile JSON, host snapshot values, then temporary CLI overrides. Existing process environment may provide secrets and documented emergency overrides, but no shell configuration file is read implicitly.

`LLMOPS_CONFIG_HOME`, `LLMOPS_DATA_HOME`, `LLMOPS_STATE_HOME`, and `LLMOPS_CACHE_HOME` select alternate roots. Installed immutable releases use their bundled `current/config` snapshot unless `LLMOPS_CONFIG_HOME` is explicitly set.

The administrator may set `deployment.source_root` in `config.json` to the clean source checkout used for packaging. `llmops deploy --source <path>` is a temporary override.

## Inventory

`inventory.json` defines hosts and transport:

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
      "transport": "ssh"
    }
  ]
}
```

Supported roles are `admin`, `llm`, `agent`, and `hybrid`. Supported transports are `local` and `ssh`.

## Components

```json
{
  "id": "chat",
  "host": "model-host",
  "driver": "modelctl",
  "profile": "chat",
  "enabled": true,
  "depends_on": [],
  "ownership": "managed",
  "health": {
    "type": "http",
    "target": "http://127.0.0.1:11434/health",
    "timeout_seconds": 60
  }
}
```

Drivers are `modelctl`, `process`, `launchd`, `model-proxy`, `tts-bridge`, `ssh-tunnel`, `agent`, and gated `command`. Generic process and agent profiles define lifecycle actions as argv arrays. There are no privileged Hermes or OpenClaw adapters.

## Secrets

Never put secret values in tracked JSON. Use environment references or provider references in profiles. Deployment snapshots reject likely embedded secret values and never include `.env` files.

For current external secret injection, launch the command with required variables already present or set `LLMOPS_ENV_FILE` to an explicit untracked file. LLM-Ops-Kit does not search `$HOME/.env`, repository `.env` files, or agent directories.

## Validation

```bash
llmops doctor
llmops config show --json
llmops component list --json
llmops plan --action start --json
```

Validation rejects missing profiles, empty inventory, unknown hosts, dependency cycles, ambiguous references, unsupported drivers, disabled command-driver use, embedded secrets, and known port conflicts.
