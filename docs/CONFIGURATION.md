# Configuration

Back: [Documentation Index](./INDEX.md)

## Authoritative Layout

```text
~/.config/llm-ops/
  config.json
  inventory.json
  stacks/*.json
  models/*.json
  agents/*.json
  services/*.json
```

Use `LLMOPS_CONFIG_HOME` only for path discovery or to select a deliberate alternate configuration root.

Installed commands automatically use `<install_root>/current/config` when that immutable release contains an authoritative snapshot. An explicit `LLMOPS_CONFIG_HOME` overrides the release snapshot.

## Precedence

Configuration resolves in this order, from lowest to highest priority:

1. Shipped defaults.
2. Global `config.json`.
3. Referenced model, agent, or service profile.
4. Host-specific values from inventory or the resolved release snapshot.
5. Temporary CLI overrides.

Environment variables are reserved for path discovery, secret injection, and documented emergency overrides. Legacy shell configuration remains a compatibility input for one release but is not part of the new authoritative model.

## Inventory

`inventory.json` names hosts and defines transport. Supported roles are `admin`, `llm`, `agent`, and `hybrid`. Supported transports are `ssh` and `local`.

```json
{
  "schema_version": 1,
  "defaults": {
    "user": "operator",
    "port": 22,
    "install_root": "~/.local/llm-ops",
    "config_profile": "default",
    "ssh_key": "~/.ssh/llmops_ed25519"
  },
  "hosts": [
    {
      "name": "model-host",
      "role": "llm",
      "host": "model-host.local"
    }
  ]
}
```

The administrator inventory is desired state. Remote changes are reported as drift and are never merged automatically.

## Components and Stacks

A component has a stable ID, inventory host, typed driver, profile reference, enabled state, dependencies, ownership, and readiness check.

```json
{
  "id": "model-proxy",
  "host": "agent-host",
  "driver": "model-proxy",
  "profile": "model-proxy",
  "enabled": true,
  "depends_on": ["chat"],
  "ownership": "managed",
  "health": {
    "type": "http",
    "target": "http://127.0.0.1:11434/health",
    "timeout_seconds": 30
  }
}
```

Supported drivers are `modelctl`, `process`, `launchd`, `model-proxy`, `tts-bridge`, `ssh-tunnel`, and `agent`. The advanced `command` driver requires `runtime.allow_command_driver: true` and accepts argv arrays only.

Ownership may be `managed` or `external`. External components can be inspected but not started, stopped, or restarted by LLM-Ops-Kit.

## Health Checks

Supported readiness checks are:

- `driver`: use the component driver's status action.
- `http`: require a successful HTTP request to the configured target.
- `tcp`: require a successful TCP connection to `host:port`.
- `none`: accept successful process start without an additional probe.

Startup waits for readiness and rolls back only components started by that invocation if the operation fails.

## Profiles

Models live under `models/`, agents under `agents/`, and proxies, bridges, launchd services, tunnels, and generic processes under `services/`.

Generic agent and process profiles declare lifecycle actions as argv arrays:

```json
{
  "schema_version": 1,
  "actions": {
    "start": ["/absolute/path/to/agent", "start"],
    "stop": ["/absolute/path/to/agent", "stop"],
    "restart": ["/absolute/path/to/agent", "restart"],
    "status": ["/absolute/path/to/agent", "status"]
  },
  "log_path": "/absolute/path/to/agent.log"
}
```

Hermes and OpenClaw compatibility profiles remain available for one release. Neither is selected implicitly.

## Secrets

Do not embed passwords, tokens, API keys, or secret values in tracked configuration. Use `env:VARIABLE_NAME` or `seckit:reference` values. Authoritative snapshot generation rejects likely embedded secret values.

Existing `.env` operation remains available during the Secrets-Kit transition. Do not synchronize `.env` files, secret values, model weights, logs, or state databases through deployment bundles.

## Validation

```bash
llmops doctor
llmops config show --json
llmops plan --action start --json
```

Validation rejects empty inventory, missing host/profile references, dependency cycles, duplicate component IDs, invalid drivers, command-driver use without its feature gate, and known port conflicts.

See [`docs/examples`](./examples) for sanitized complete examples.
