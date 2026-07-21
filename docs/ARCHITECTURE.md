# Architecture

**Created**: 2026-07-16
**Updated**: 2026-07-21

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

Component start satisfies missing upstream dependencies. Component restart affects only the target by default. Component stop refuses active dependents unless `--force` or `--cascade` is used. CLI and TUI call the same mutation preparation service, so interface code cannot bypass dependent-impact checks. Stack operations start in dependency order and stop in the exact reverse of the selected startup order.

The executor is idempotent. A failed start stops only components started by that invocation and leaves pre-existing services untouched. Mutations use a lifecycle lock; status, health, drift, plans, effective configuration, and logs are read-only. Interactive clients dispatch long-running mutations to detached short-lived workers that persist an operation record. No privileged daemon is required, and closing a client does not cancel an accepted operation.

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
| Operation records | Persist accepted command, plan, target host, progress, bounded output, error, and result for detached work | Lifecycle planning or a resident daemon |
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
install -> repair -> update_check -> update_plan -> update_apply -> update_rollback -> uninstall
relocation_preflight -> relocation_cutover -> relocation_rollback
observe -> metrics -> drift -> corrective_actions
```

## Service Templates And Schema

Canonical schema version 2 binds every component and reusable profile to a versioned service template. Templates use JSON Schema 2020-12 plus a constrained `x-llmops-ui` vocabulary for presentation only. They declare typed parameters, constraints, lifecycle ownership, argument arrays, endpoint contracts, readiness, timeouts, restart policy, logs, and reviewed adapter-owned actions.

The CLI and TUI consume the same field model. Typed `--set` and `--unset`, generated forms, local-template import, endpoint wiring, and validation therefore cannot diverge into interface-specific configuration behavior. Local templates may select only registered adapters, argument arrays, and approved option sources; Python callbacks and shell strings are rejected.

Connections reference typed provider endpoints. A required endpoint implies a lifecycle dependency unless the template explicitly opts out. Address resolution occurs when target-specific snapshots are reconciled, so reusable profiles are not rewritten with one host's resolved address.

One host named by `control.authority_host` owns mutable desired state. Trusted peers carry the same secret-free catalog and may request a mutation, but the operation is forwarded to the authority with the observed authority hash. Stale hashes are refused and independent edits are never merged.

Tool components represent installed command-line integrations that do not have start or stop semantics. RTK is the first built-in tool template: status checks installation, while version, telemetry, verification, gain, and Hermes dry-run are explicit actions. Mutating canary retention remains gated by backup and rollback acceptance.

Update capability metadata distinguishes check, plan, apply, backup, rollback, and post-update health support. Relocation capability metadata distinguishes stateless ownership, preflight, cutover, and rollback. Built-in adapters do not advertise mutating update or relocation capabilities until their native implementations pass failure and rollback acceptance.

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

Lifecycle, readiness, SSH, and log timeouts are explicit canonical component values. They are consumed identically by CLI and TUI operations and never inferred from an interactive shell environment.

Model weights, agent databases, Vaults, conversation history, generated media, and voice samples remain owned by their respective systems. TTS Bridge may map operator-defined aliases to operator-provided reference material, but LLM-Ops-Kit does not ship voice samples.

## Remote Operation and Synchronization

The desired-state authority produces checksummed configuration snapshots. Trusted control hosts receive the complete secret-free topology and referenced profiles so status, dependency plans, and authorized lifecycle operations are consistent from either controller. Component-only hosts receive only the profiles required to operate their components.

Remote execution uses configured transports and absolute command paths. SSH is the initial transport. A target does not need a source checkout or an interactive shell. Independent edits are reported as drift and never merged automatically.

Lifecycle adapters operate on the host that owns the subsystem. A control interface may run anywhere with an authorized route to that host. Container and cloud integrations are endpoints behind adapters, not resources scheduled by LLM-Ops-Kit.

## Operator Interfaces

The first graphical interface is a Textual TUI that runs on demand and requires no daemon. Its beta scope is:

- Global and per-host lifecycle, health, condition, observability, version, drift, and authority.
- Component and stack drill-down.
- Start, stop, restart, logs, plans, and update checks.
- Schema-generated creation and editing for reviewed templates, reusable profiles, endpoint connections, and component lifecycle metadata.
- High-contrast keyboard and mouse navigation, local refresh settings, shared display labels, and contextual help.
- A bounded host-grouped topology view with immediate dependency relationships and filters.
- Equivalent CLI display before every mutation.

The status model keeps lifecycle, health, and observation policy independent. A process may be running while its readiness check is degraded. A component may be known but `authority-only`, which is unobserved rather than unreachable. Toolkit and component versions are separate fields.

Configured and observed runtime identities are also independent. The desired runtime comes from the selected immutable release; the observed runtime is derived from the live process command or adapter probe. A live process from an older release is reported as stale and requires attention without being falsely described as stopped.

Local TUI preferences live in `ui.json` and are excluded from desired-state hashes. Organization and site labels live in canonical configuration and reconcile normally.

The optional WebUI is a separate loopback-only control process serving static HTML, CSS, and JavaScript through a small API layer. It uses the same control library and operation schema, remains available while models and agents are stopped, and uses SSH tunnels or an explicitly configured HTTPS endpoint for remote access. It is not required for CLI or TUI operation.

## Packaging

The distribution is a standard `src/llmops_kit` Python package installed into an application-owned UV environment with locked CPython 3.12 dependencies and declared console entry points. Runtime shell scripts remain only for bootstrap and native service integration. Templates and service resources are versioned release assets. The installer reuses the audited Secrets-Kit bootstrap pattern where applicable, supports checksum verification and rollback, and does not require a Git checkout, system Python, Conda, or shell-profile activation.

## Prompt Diagnostics And Media History

Model-proxy is a passive transport and observability tap: the upstream request and downstream response bodies are forwarded unchanged. Optional Jinja rendering is diagnostic and supplies a model-engine chat template; it is not proxy rewriting.

The unchanged stock Qwen template remains the reference. The optional media-history template uses message roles and explicit tool-response structure to remove costly historical image payloads and assistant calls that copy those bytes. It temporarily preserves the final image-bearing textual tool response and preserves native structured image and video parts. Portable Jinja does not validate base64; complete captured fixtures and offline diagnostics own that decision.

The normal beta installation includes Textual. `--minimal` omits the TUI and its dependencies. Integration-specific dependencies remain optional. Release artifacts contain no private topology, model weights, voice samples, credentials, tests, or development history.
