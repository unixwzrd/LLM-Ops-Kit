# Architecture

**Created**: 2026-07-16
**Updated**: 2026-07-19

Back: [Documentation index](./INDEX.md)

## Product Boundary

LLM-Ops-Kit is a lightweight control plane for heterogeneous AI components. It discovers, configures, validates, operates, and observes models, agents, proxies, bridges, memory systems, tunnels, and supporting services without replacing their native execution environments.

It is not a container scheduler, model engine, agent, secret store, virtual machine manager, or distributed consensus system. launchd, systemd, standalone processes, SSH, containers, and external service managers continue to own process execution and isolation. LLM-Ops-Kit coordinates them through typed lifecycle adapters.

## Control Flow

```text
CLI ---------+
Textual TUI -+--> operation model --> validation --> planner --> executor --> adapter --> transport --> target
Web API -----+
Agent skill -+
                       |              |              |
                       +-> CLI view   +-> audit      +-> status and events
```

The reusable control library is authoritative. `llmops` is the canonical public command surface and automation contract. The TUI, optional WebUI, and future agent skill consume the same operation model and control interfaces; they do not shell out to reimplement orchestration. Every mutation displays an equivalent `llmops` invocation for reproducibility in DevOps, MLOps, scripts, and CI.

Canonical configuration is converted into a validated topology, dependency plan, typed adapter operation, and local or remote transport action:

```text
canonical configuration -> schema validation -> topology -> dependency plan -> adapter -> local or remote transport
```

Component start satisfies missing upstream dependencies. Component restart affects only the target by default. Component stop refuses active dependents unless `--force` or `--cascade` is used. Stack operations compose the same component planner in dependency order.

The executor is idempotent. A failed start stops only components started by that invocation and leaves pre-existing services untouched. Mutations use a lifecycle lock; status, health, drift, plans, and logs are read-only.

## Module Boundaries

| Module | Responsibility | Must not own |
|---|---|---|
| Configuration | Load, merge, normalize, validate, and transactionally write canonical configuration | Process lifecycle or remote execution |
| Schema registry | Core schemas plus adapter-provided schema fragments and UI metadata | Product-specific business logic |
| Inventory and topology | Hosts, transports, component identities, tags, dependencies, and authority | Secrets or process handles |
| Planner | Dependency ordering, impact analysis, idempotence decisions, rollback scope, and equivalent CLI rendering | Direct subprocess or SSH calls |
| Executor | Apply approved plans, locks, partial-start cleanup, timeouts, and event emission | Configuration discovery or UI state |
| Adapter registry | Discover compatible, versioned lifecycle and subsystem adapters | Implicit network installation |
| Transports | Local execution, SSH, and future constrained remote transports | Component-specific command construction |
| Distribution and reconciliation | Checksummed release artifacts, immutable updates, role-filtered configuration revisions, drift, and rollback | Model weights, agent state, or secret values |
| Observability | Status, health, drift, logs, model-proxy exchanges, and corrective-action rules | Prompt mutation or autonomous remediation |
| Interfaces | CLI, TUI, HTTP API, static WebUI, and agent skill | Independent planners or executors |

## Adapter Model

Adapters are independently testable modules registered through Python entry points. Adding a subsystem should not require editing the planner, executor, CLI parser, TUI screens, or WebUI.

An adapter manifest declares:

- Stable adapter ID, semantic version, and compatibility range.
- Adapter kind and capabilities such as lifecycle, status, logs, configuration, installation, updates, or observability.
- Supported platforms and required executables.
- Configuration schema fragments, defaults, validation rules, and non-secret UI metadata.
- Health/readiness behavior, timeout defaults, and lifecycle ownership.
- Whether remote operation is permitted and which transports are supported.

The initial lifecycle adapter contract provides typed methods equivalent to:

```text
validate -> plan -> status -> health -> start -> stop -> restart -> logs
```

Optional capability interfaces provide:

```text
install -> repair -> update_check -> update_plan -> uninstall
observe -> metrics -> drift -> corrective_actions
```

All mutating methods receive an approved plan and argument arrays. Adapters must not accept unvalidated shell strings, embed secrets in returned plans, silently install dependencies, or mutate unrelated component state. Corrective actions are deterministic rules with evidence and an equivalent CLI plan; LLM-Ops-Kit does not act as an agent.

Adapters are grouped by responsibility rather than vendor:

- Lifecycle backends: launchd, systemd, standalone managed process, SSH tunnel, and future container endpoints.
- Model engines: llama.cpp initially, followed by an explicitly early-alpha MLXForge adapter.
- Agents: generic process or service profiles, plus optional Hermes and OpenClaw setup recipes.
- Supporting systems: model-proxy, tts-bridge, Mnemosyne, RTK, Headroom, dashboards, and other independently manageable services.
- Observability extensions: model-proxy request/rendered-prompt/response correlation, health metrics, logs, and drift providers.

Product integrations remain optional packages or extras when they add dependencies. The core must remain usable without Textual, FastAPI, a model engine, or an agent framework.

## Configuration and Secrets

One versioned schema drives CLI validation, guided initialization, TUI forms, WebUI forms, documentation examples, and adapter tests. Schema metadata may include labels, descriptions, groups, ordering, secret-reference types, validation constraints, and conditional fields.

Precedence remains:

```text
shipped defaults -> global configuration -> referenced profile -> host override -> temporary CLI override
```

Configuration contains secret references, never resolved secret values in plans, topology catalogs, interface state, or logs. Existing environment injection remains transitional. Secrets-Kit may later implement a provider interface without becoming a hard dependency.

Model weights, agent databases, Vaults, conversation history, generated media, and voice samples remain owned by their respective systems. TTS Bridge may map operator-defined aliases to operator-provided reference material, but LLM-Ops-Kit does not ship voice samples.

## Remote Operation and Synchronization

The desired-state authority produces checksummed, role-filtered snapshots. Trusted control hosts receive the complete secret-free topology catalog so status and plans are consistent, while target hosts receive only the profiles required to operate their components.

Remote execution uses configured transports and absolute command paths. SSH is the initial transport. A target does not need a source checkout or an interactive shell. Independent edits are reported as drift and never merged automatically.

Lifecycle adapters operate on the host that owns the subsystem. A control interface may run anywhere with an authorized route to that host. Container and cloud integrations are endpoints behind adapters, not resources scheduled by LLM-Ops-Kit.

## Operator Interfaces

The first graphical interface is a Textual TUI that runs on demand and requires no daemon. Its beta scope is:

- Global and per-host status, health, version, drift, and authority.
- Component and stack drill-down.
- Start, stop, restart, logs, plans, and update checks.
- Schema-driven configuration forms with validation.
- Deterministic corrective-action suggestions.
- Equivalent CLI display before every mutation.
- Model-proxy request, rendered-prompt, response, timing, and error correlation without changing proxied traffic.

The optional WebUI is a separate loopback-only control process serving static HTML, CSS, and JavaScript through a small API layer. It uses the same control library and operation schema, remains available while models and agents are stopped, and uses SSH tunnels or an explicitly configured HTTPS endpoint for remote access. It is not required for CLI or TUI operation.

## Packaging

The distribution is a standard `src/llmops_kit` Python package installed into an application-owned UV environment with locked CPython 3.12 dependencies and declared console entry points. Runtime shell scripts remain only for bootstrap and native service integration. Templates and service resources are versioned release assets. The installer reuses the audited Secrets-Kit bootstrap pattern where applicable, supports checksum verification and rollback, and does not require a Git checkout, system Python, Conda, or shell-profile activation.

The normal beta installation includes Textual. `--minimal` omits the TUI and its dependencies. Integration-specific dependencies remain optional. Release artifacts contain no private topology, model weights, voice samples, credentials, tests, or development history.
