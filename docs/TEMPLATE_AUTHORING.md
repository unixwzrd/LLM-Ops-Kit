# Service Template Authoring

**Created**: 2026-07-21
**Updated**: 2026-07-21

Back: [Documentation index](./INDEX.md)

LLM-Ops-Kit service templates are reviewed JSON Schema 2020-12 documents. Built-ins are package resources. Operator templates are imported into `~/.config/llm-ops/templates/` and become part of the authority hash and reconciled snapshots.

## Contract

A template declares a stable ID and version, registered adapter, component and profile kinds, supported platforms, lifecycle, restart policy, profile schema/defaults, argument-array bindings, endpoints, logs, and optional adapter-owned actions.

Allowed lifecycles are `standalone`, `launchd-user`, `external-launchd`, `ssh-tunnel`, `external`, `tool`, and experimental `systemd-user`. Local templates may not contain shell command strings or Python callbacks. Actions are argument arrays and may reference an entire scalar profile field with `{profile.path}`.

Use standard JSON Schema constraints, including `enum`, ranges, patterns, `oneOf`, `not`, `if/then/else`, and `dependentRequired`. `x-llmops-ui` may define `label`, `group`, `order`, `widget`, `help`, `advanced`, and an approved `options_source`. Shipped schemas are reviewed; executable `--help` output is not an authority.

## Validation and Import

```bash
llmops template doctor
llmops template import ./my-service.json --plan
llmops template import ./my-service.json --apply --yes
llmops template fields my-service
```

Import is transactional and refuses duplicate IDs. A local template can add a generic service without modifications to the planner, executor, CLI parser, or TUI.

## Connections

Providers declare named endpoints. Consumers declare required endpoint names and protocols. Components bind them by stable component ID:

```json
{
  "connections": {
    "upstream": {
      "component": "local-ai:chat",
      "endpoint": "openai"
    }
  }
}
```

Bind addresses describe the provider process. Advertised addresses are resolved for the consuming target during reconciliation; reusable source profiles are not rewritten.
