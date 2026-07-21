# Status Semantics

**Created**: 2026-07-21
**Updated**: 2026-07-21

Back: [Documentation index](./INDEX.md)

`llmops status`, component status, stack status, JSON output, and the Textual console consume one shared observation record. Status is intentionally not compressed into one ambiguous field.

| Field | Values | Meaning |
|---|---|---|
| `lifecycle` | `running`, `stopped`, `disabled`, `unknown` | Whether the process or native service exists |
| `health` | `healthy`, `degraded`, `unhealthy`, `unknown`, `not-applicable` | Whether the running component passes its readiness check |
| `condition` | `ok`, `attention`, `error`, `unobserved` | Operator-facing severity derived from lifecycle, health, drift, and observability |
| `observability` | `observed`, `authority-only`, `unreachable` | Whether this host has and successfully used an authorized observation route |

A running model-proxy whose upstream model is unavailable is `lifecycle=running`, `health=degraded`, and `condition=attention`. It is not reported as stopped merely because its health command exits nonzero.

`authority-only` means the topology catalog knows the component but the current host lacks an authorized observation route. It is represented as `observability=authority-only`, `lifecycle=unknown`, and `condition=unobserved`. It does not assert that the component is running or stopped.

`toolkit_version` identifies the observing LLM-Ops-Kit runtime. `component_version` identifies the observed component runtime when its adapter, profile, or immutable runtime path provides that information. They are not interchangeable.

The removed legacy `status` alias is not present in beta JSON records.

## Exit Codes

| Exit | Meaning |
|---|---|
| `0` | All records are `ok` or `unobserved` |
| `1` | At least one record requires `attention`, with no `error` |
| `2` | At least one record is `error`, or status configuration is invalid |

Examples:

```bash
llmops status
llmops status model-proxy --json
llmops component status model-proxy --json
llmops stack status <stack> --json
```
