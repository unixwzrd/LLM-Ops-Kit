# Status Semantics

**Created**: 2026-07-21
**Updated**: 2026-08-20

Back: [Documentation index](./INDEX.md)

`llmops status`, component status, stack status, JSON output, and the Textual console consume one shared observation record. Status is intentionally not compressed into one ambiguous field.

| Field | Values | Meaning |
|---|---|---|
| `lifecycle` | `running`, `stopped`, `disabled`, `unknown`, or a transient operation state | Whether the process or native service exists or an approved operation is in progress |
| `health` | `healthy`, `degraded`, `unhealthy`, `unknown`, `not-applicable` | Whether the running component passes its readiness check |
| `uptime` | compact duration, `unknown`, or `-` | How long the observed process or native service has been running, independent of health |
| `uptime_seconds` | non-negative integer or `null` | Machine-readable elapsed runtime |
| `started_at` | ISO-8601 timestamp or empty | Observed or derived process start time |
| `uptime_source` | `process`, `state`, `state-invalid`, `unknown`, or empty | Provenance for the uptime observation |
| `desired_lifecycle` | `running`, `stopped`, `disabled` | Last successful lifecycle intent recorded by LLM-Ops-Kit |
| `condition` | `ok`, `down`, `attention`, `error`, `unobserved` | Operator-facing state derived from lifecycle, desired lifecycle, health, drift, and observability |
| `observability` | `observed`, `authority-only`, `unreachable` | Whether this host has and successfully used an authorized observation route |
| `execution_user` | configured account name | Identity LLM-Ops-Kit uses for lifecycle operations on the component host |

A running model-proxy whose upstream model is unavailable is `lifecycle=running`, `health=degraded`, and `condition=attention`. It is not reported as stopped merely because its health command exits nonzero.

Uptime follows the component process or native service, not readiness. A degraded component therefore keeps accumulating uptime; restarting its process resets the value. Components without a process identity, such as an installed command-line tool, report `uptime=unknown` rather than inventing a start time. Stopped and disabled components display `-`.

An operator-requested stop is `lifecycle=stopped`, `desired_lifecycle=stopped`, and `condition=down`. It is expected and returns status exit code 0. An enabled component that is stopped while `desired_lifecycle=running` is an error. Desired lifecycle state is stored transactionally under the operational state root and survives immutable runtime updates.

`authority-only` means the topology catalog knows the component but the current host lacks an authorized observation route. It is represented as `observability=authority-only`, `lifecycle=unknown`, and `condition=unobserved`. It does not assert that the component is running or stopped.

`toolkit_version` identifies the observing LLM-Ops-Kit runtime. `component_version` identifies the observed component runtime when its adapter, profile, or immutable runtime path provides that information. They are not interchangeable.

`desired_runtime` is the immutable release selected by configuration. `observed_runtime` is derived from the live process command when available. A mismatch sets `runtime_drift=true`, reports `drift=stale-runtime`, and raises `condition=attention` without falsely claiming the process is stopped.

`execution_user` appears as `RUN_AS` in human output. It is configuration-backed and identifies the account used for lifecycle operations; it does not claim that every child process owner was independently inspected.

The removed legacy `status` alias is not present in beta JSON records.

## Exit Codes

| Exit | Meaning |
|---|---|
| `0` | All records are `ok`, `down`, or `unobserved` |
| `1` | At least one record requires `attention`, with no `error` |
| `2` | At least one record is `error`, or status configuration is invalid |

Examples:

```bash
llmops status
llmops status model-proxy --json
llmops component status model-proxy --json
llmops stack status <stack> --json
llmops component version <component>
llmops operation list
llmops operation show <operation-id>
```
