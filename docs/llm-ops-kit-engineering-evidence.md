# LLM-Ops-Kit Engineering Evidence

- **Evidence updated:** 2026-07-21
- **Accepted live candidate:** `0.9.0b11`
- **Current source candidate:** `0.9.0b11`
- **Candidate runtime artifact source commit:** `72e9a7f`
- **Candidate release archive SHA-256:** `2e86f4db48800f7a077ecfc0a33680e5c83a431156067f76f05293ed6cacd3e6`

## Purpose

This report explains the architectural invariants of LLM-Ops-Kit and the acceptance evidence supporting them. It is intended for engineers who have not worked on the project. It does not publish private addresses, credentials, model paths, voice samples, prompts, or site-specific configuration.

LLM-Ops-Kit is a lightweight control plane for heterogeneous AI services. It coordinates existing process managers, model engines, agents, proxies, bridges, dashboards, and tunnels through typed adapters. It does not replace launchd, SSH, model runtimes, containers, secret stores, or agent frameworks.

The central correctness argument is that LLM-Ops-Kit separates desired state, planning, execution, observation, and product-specific lifecycle behavior. Mutations are derived from validated configuration, represented as inspectable plans, executed by typed adapters, bounded by dependency and rollback rules, and verified against immutable release and configuration identities.

## Evidence Scope

The full two-host and protocol acceptance baseline was collected against `0.9.0b4`. It included exact-artifact installation on Apple Silicon and Intel macOS, rollback and return, bidirectional remote lifecycle operations, a dependency-ordered cold stop/start, model-proxy chat, 1,024-dimensional embeddings, cloned-voice TTS, agent services, dashboards, optimization services, and the Desktop tunnel.

Accepted runtime baseline `0.9.0b5` added a shared catalog-aware status collector and was installed on both live macOS hosts through coordinated update. Its shared catalog and host-specific configuration hashes remained unchanged, and all observable services remained running.

Candidate `0.9.0b11` separates lifecycle, health, condition, and observability; separates toolkit, component, desired-runtime, and observed-runtime identities; reports the configured execution identity; centralizes dependent-impact enforcement across CLI and TUI; and adds the high-contrast, keyboard-accessible, configurable TUI and bounded topology projection. It also adds host-qualified log inspection, effective configuration inspection, configurable lifecycle timeouts, persistent detached operations, authority-backed reconciliation, structurally pruned historical media decode/save calls, and model start-runtime provenance. The exact candidate archive was installed on both live hosts, its model, proxy, and bridge components were restarted, and both trusted hosts returned the same global status view.

## Topology And Trust Boundary

```mermaid
flowchart LR
    Operator["Operator"] --> CLI["llmops CLI"]
    Operator --> TUI["Textual TUI"]
    CLI --> Control["Shared control library"]
    TUI --> Control
    Control --> Validate["Schema and topology validation"]
    Validate --> Planner["Dependency planner"]
    Planner --> Executor["Executor and lifecycle lock"]
    Executor --> Local["Local typed adapter"]
    Executor --> SSH["SSH transport"]
    Local --> ModelHost["Model host: chat, embeddings, TTS"]
    SSH --> AgentHost["Agent host: agent, proxy, bridge, dashboard"]
    SSH --> ModelHost
    Control --> Catalog["Secret-free observer catalog"]
    Authority["Desired-state authority"] --> Revisions["Checksummed role-filtered configuration revisions"]
    Revisions --> AgentHost
    Revisions --> ModelHost
    Authority --> Catalog
    Secrets["External secret provider or environment"] -. "references only" .-> AgentHost
    Secrets -. "references only" .-> ModelHost
```

The authority is the only source of desired state. Trusted control hosts receive the complete secret-free topology needed to plan and observe authorized operations. Component hosts receive only the profiles required for their role. Secret values, model weights, runtime logs, state databases, and agent data are excluded from synchronization.

This arrangement is correct for a small trusted LAN control plane because it avoids an unsolved distributed-consensus problem. Independent remote edits are detected as drift and refused rather than merged. Operators therefore get deterministic behavior without pretending that several writable replicas can reconcile arbitrary changes safely.

## Architectural Invariants

| Invariant | Enforcement mechanism | Acceptance evidence | Failure prevented |
|---|---|---|---|
| One desired-state authority | Canonical configuration is rendered into checksummed host revisions; remote edits are never merged | A deliberate remote edit produced `conflict`; reconciliation refused replacement; restoring the backup returned validation to clean | Split-brain configuration and silent loss of an operator change |
| Plans precede mutations | CLI and TUI use the same mutation preparation service; active-dependent impact and equivalent CLI commands are resolved before confirmation | Headless TUI tests verify equivalent commands, cancellation, and mandatory dependent-impact choice | A UI-specific orchestration path bypassing lifecycle safety |
| Dependencies determine order | Start uses topological order; stop uses reverse topological order; cycles are rejected during validation | Unit tests verify dependency-first start and reverse stop; live cold-cycle acceptance stopped and started the complete stack in the expected order | Starting consumers before providers or stopping providers under active consumers |
| Failure cleanup is bounded | The executor records components started by the current invocation and only stops that set on failure | Regression injects a failed start while a pre-existing service remains running | A failed operation taking down unrelated healthy services |
| Releases are immutable and reversible | Each release is installed under a versioned directory; `current` and `previous` are atomically selected | Both hosts rolled back from `0.9.0b4` to `0.9.0b3` and returned; the `0.9.0b5` update retained `0.9.0b4` as `previous` | In-place partial upgrades and unrecoverable runtime replacement |
| Coordinated update is all-or-rollback | All selected hosts preflight before apply; the same verified archive is staged; apply is sequential; changed hosts roll back if a later host fails | Tests inject second-host failure and verify rollback of the first; the live two-host update installed one archive and verified version/config/catalog identity | Silent mixed-version operation after a partial update |
| Configuration selection is atomic | Accepted revisions are immutable and `current-config` selects one revision; replacement creates a backup | Reconciliation applied once, a second plan was a no-op, and manually divergent content was refused | Processes reading a half-written configuration tree |
| Observation separates lifecycle from readiness | Lifecycle, health, condition, and observability are independent fields; readiness failure cannot silently become stopped lifecycle | A proxy fixture and live read-only source probe report a running proxy with failed upstream health as `running/degraded/attention` | Restarting or stopping a live process because its dependency is temporarily unavailable |
| Observation respects authorization | The observer catalog marks hosts as peer-observable or authority-only; status distinguishes policy from transport failure | Both trusted hosts produced the same component set; the local Desktop tunnel is `unknown/unknown/unobserved` with `authority-only` observability | False outage alarms for resources a peer is intentionally unable to inspect |
| Product integrations do not invade the core | Versioned adapters own lifecycle details; planner, executor, CLI, and TUI consume the registry | Six built-in adapters passed discovery and conformance; a fixture adapter registers without core parser or planner changes | Vendor-specific conditionals spreading through orchestration code |
| Runtime Python is application-owned | UV installs locked dependencies into each immutable release and wrappers use absolute release paths | Exact artifacts installed without Git, system Python, Conda activation, shell-profile sourcing, or a checkout on both macOS architectures | Launchd and SSH selecting an accidental or incompatible Python environment |
| Proxies are observational, not mutating | Model-proxy forwards the original request and performs template rendering only in a diagnostic path | Clean-artifact proxy rendering and protocol acceptance passed while raw upstream behavior remained unchanged | Debug tooling changing production prompts |
| Interactive clients do not own operation lifetime | The TUI records an accepted command and plan, then launches a detached short-lived worker using the same packaged control library | Regression verifies detached process flags, transactional progress records, bounded output/error capture, and TUI dispatch without waiting | Closing a terminal cancelling a model startup or hanging for executor thread shutdown |
| Runtime identity follows the live process | Desired release identity and observed process release identity are reported independently | Regression extracts an immutable release from the running command and classifies a mismatch as stale runtime | A current CLI masking a service still running old code |

## Update Protocol

```mermaid
sequenceDiagram
    participant O as Operator
    participant A as Authority
    participant H1 as Host A
    participant H2 as Host B
    O->>A: llmops update --all-hosts --plan
    A->>H1: Preflight platform, disk, schema, installer, current version
    A->>H2: Preflight platform, disk, schema, installer, current version
    alt any preflight fails
        A-->>O: Refuse before mutation
    else all preflights pass
        A->>H1: Stage and verify the same checksummed archive
        A->>H2: Stage and verify the same checksummed archive
        A->>H1: Install immutable release and verify identities
        A->>H2: Install immutable release and verify identities
        alt Host B apply or verification fails
            A->>H1: Roll back release changed by this invocation
            A-->>O: Report original and rollback results
        else both verify
            A-->>O: Report versions, catalog hash, and configuration hashes
        end
    end
```

The protocol is safe because preflight is complete before the first mutation, every host receives the same content-addressed input, and rollback scope is limited to hosts changed by that invocation. The protocol is observable because success includes runtime, catalog, and configuration identities rather than relying on process exit status alone.

The protocol is deliberately sequential. For a small local AI topology, bounded interruption and straightforward rollback are more valuable than parallel rollout complexity. Sequential application also makes the changed-host set unambiguous when a later host fails.

## Runtime Rollback

```mermaid
stateDiagram-v2
    [*] --> StableA: current = release A
    StableA --> InstallingB: verify archive and stage release B
    InstallingB --> StableA: installation or verification fails
    InstallingB --> StableB: atomically set current = B and previous = A
    StableB --> StableA: rollback exchanges current and previous
    StableA --> StableB: rollback again returns to B
```

Rollback is a pointer exchange between immutable releases, not reconstruction from a mutable working directory. This matters because the old executable, package environment, templates, and native resources remain a coherent unit. The configuration tree is separate durable state, so normal runtime rollback does not erase operator configuration or agent data.

## Accepted Start And Stop Ordering

```mermaid
flowchart TB
    subgraph Startup["Startup: dependency-first topological order"]
        direction LR
        S1["1. Chat model"] -. "next plan step" .-> S2["2. Model proxy"]
        S2 -.-> S3["3. Context optimizer"]
        S3 -.-> S4["4. Embedding model"]
        S4 -.-> S5["5. TTS model"]
        S5 -.-> S6["6. TTS bridge"]
        S6 -.-> S7["7. Agent gateway"]
        S7 -.-> S8["8. Dashboard"]
        S8 -.-> S9["9. Desktop tunnel"]
    end

    subgraph Shutdown["Shutdown: exact reverse of startup"]
        direction LR
        X9["1. Desktop tunnel"] -. "next plan step" .-> X8["2. Dashboard"]
        X8 -.-> X7["3. Agent gateway"]
        X7 -.-> X6["4. TTS bridge"]
        X6 -.-> X5["5. TTS model"]
        X5 -.-> X4["6. Embedding model"]
        X4 -.-> X3["7. Context optimizer"]
        X3 -.-> X2["8. Model proxy"]
        X2 -.-> X1["9. Chat model"]
    end

    Startup ~~~ Shutdown
```

The dotted arrows show the accepted plan sequence, not additional dependency edges. Independent branches may have more than one valid topological ordering, but once the planner selects a deterministic startup order, full-stack shutdown reverses that exact list. The accepted nine-component stop plan was mechanically compared with the start plan and matched it in reverse.

The planner treats components as a directed acyclic graph. Starting a target includes missing upstream dependencies. Stopping a component with active dependents requires confirmation, force, or cascade. Restart affects only the target by default, which allows a model engine to be replaced or bounced without restarting the agent and proxy layers.

Correctness has two parts. First, graph validation rejects cycles and unknown dependencies before execution, so an order always exists. Second, the executor tracks pre-existing state. If a multi-component start fails, it reverses only starts completed by that invocation, preserving services that were already healthy.

## Configuration Reconciliation

```mermaid
flowchart TD
    Desired["Canonical desired state"] --> Render["Render role-filtered snapshot"]
    Render --> Hash["Per-file hashes and resolved manifest"]
    Hash --> Inspect["Inspect remote current-config"]
    Inspect -->|"same hash"| Noop["No-op"]
    Inspect -->|"unreachable or invalid"| Refuse["Refuse and report"]
    Inspect -->|"independent edit"| Conflict["Conflict: never merge"]
    Inspect -->|"known prior revision"| Confirm["Show plan and require confirmation"]
    Confirm --> Backup["Record previous revision"]
    Backup --> Transfer["Transfer complete immutable snapshot"]
    Transfer --> Verify["Verify manifest and hashes"]
    Verify --> Atomic["Atomically select current-config"]
```

Reconciliation is idempotent because identical hashes produce a no-op. It is conservative because invalid, unreachable, or independently modified targets block application. It is recoverable because accepted snapshots are immutable, the prior selection is recorded, and the active selection changes only after the complete snapshot verifies.

Trusted controllers receive a complete secret-free catalog so each can produce the same global status and authorized plans. Runtime component hosts still consume host-specific configuration revisions, which is why their configuration hashes legitimately differ while their shared catalog hash agrees.

## Status Semantics

Status is a structured observation rather than a Boolean or overloaded string:

- `lifecycle` reports `running`, `stopped`, `disabled`, or `unknown`.
- `health` reports `healthy`, `degraded`, `unhealthy`, `unknown`, or `not-applicable`.
- `condition` reports `ok`, `attention`, `error`, or `unobserved`.
- `observability` reports `observed`, `authority-only`, or `unreachable`.

This distinction prevents readiness and policy from being misreported as lifecycle. A live proxy with an unavailable upstream is running but degraded. A Desktop tunnel that cannot be inspected from a peer is unknown and unobserved, not unreachable. The former `status` alias is absent from candidate JSON records.

## Acceptance Record

| Evidence | Result |
|---|---|
| Candidate source regression | Commit `72e9a7f` passed 142 tests, shell syntax, ShellCheck, Python compilation, adapter checks, archive audits, and maintainer precheck |
| Candidate clean distribution | Runtime-only `0.9.0b11` archive built from `git archive HEAD`; isolated minimal installation, version, adapter doctor, uninstall, and purge passed |
| Candidate installed-wheel tests | Six Textual tests and 42 control-plane tests passed with repository source removed from `PYTHONPATH` |
| Clean distribution | Runtime-only archive built from clean commit `6989f97` |
| Release identity | Version `0.9.0b5`; archive SHA-256 `8169e9c6f953a3036c1c5e30aa2868ac4e9ab704172c5074c184d71140076b8f` |
| macOS packaging baseline | Exact-artifact normal and minimal installation previously passed on Apple Silicon and Intel isolated users |
| Live coordinated update | Both managed hosts advanced from `0.9.0b4` to `0.9.0b5`; both retained `0.9.0b4` as `previous` |
| Configuration preservation | Shared catalog hash and both host-specific configuration hashes were unchanged after update |
| Runtime continuity | Eight remotely observable components remained running; the local Desktop tunnel remained correctly classified as `authority-only` |
| Cross-host lifecycle baseline | Model, proxy, bridge, and complete dependency-ordered stack operations passed in both directions |
| Protocol baseline | Chat, 1,024-dimensional embeddings, WAV TTS, gateway, dashboard, optimization proxy, and tunnel checks passed |
| Reconciliation | Apply, idempotent no-op, conflict refusal, backup restoration, and clean manifest verification passed |
| Failure injection | Partial-start cleanup, second-host update failure rollback, tampered artifact rejection, unreachable host handling, and invalid configuration refusal passed |
| Candidate live acceptance | Both hosts installed `0.9.0b11` with `0.9.0b10` retained as `previous`; chat, embedding, TTS, model-proxy, and tts-bridge restarted healthy and reported matching desired/observed b11 runtime. Both trusted hosts reported eight healthy observable components and one consistently unobserved authority-owned Desktop tunnel. The final rollback/return and complete cold-cycle remain open. |
| Candidate media replay | Authoritative raw request replay through the installed media-history template produced 260,840 rendered bytes, one image result, one PNG marker, zero assistant decode/copy calls, and one preserved truncation marker |

## Why The Evidence Is Sufficient

Unit and integration tests establish local invariants such as graph ordering, bounded rollback, adapter conformance, schema rejection, artifact verification, and interface equivalence. Exact-artifact installation establishes that the release does not depend on ignored checkout residue or a developer Python environment. Two-host acceptance establishes that SSH addressing, absolute runtime paths, role-filtered configuration, trusted peer control, and shared catalog semantics work outside fake transports. Protocol tests establish that successful lifecycle status corresponds to usable model and agent endpoints rather than merely existing processes.

No single layer is treated as conclusive. The evidence chain is configuration identity, plan behavior, lifecycle result, health observation, and protocol response. That layered approach is why live acceptance exposed earlier defects in runtime wrapper configuration selection and SSH `control_host` use even though narrower tests had passed.

## Non-Claims And Remaining Gates

- macOS is the supported beta platform. Linux and systemd work remain experimental and are not publication claims.
- LLM-Ops-Kit is not a high-availability consensus system. It intentionally uses one desired-state authority and conflict refusal.
- `authority-only` does not prove that the component is running; it states that the current peer is not an authorized observer. The authority must inspect that component.
- The current beta does not download models, install arbitrary engines, edit raw secrets, or autonomously remediate failures.
- The Textual TUI is an on-demand client, not a daemon. A future WebUI must use the same control interfaces rather than create a second executor.
- The `0.9.0b11` candidate remains local and unpublished. Publication is gated on prompt replay, clean-artifact acceptance, two-host live acceptance, explicit maintainer approval, and green macOS CI.

## Reproduction Outline

An independent maintainer can reproduce the public evidence without the private topology:

```bash
scripts/precheck
python scripts/build-release.py --output-dir /tmp/llmops-release
shasum -a 256 /tmp/llmops-release/LLM-Ops-Kit-*.tar.xz
llmops doctor --probe
llmops status --json
llmops plan --action start --json
llmops config reconcile --all-hosts --plan --json
llmops update --all-hosts --plan --archive /path/to/release.tar.xz --checksum-file /path/to/release.tar.xz.sha256 --json
```

Fresh installation, rollback, uninstall, purge, TUI, lifecycle, and protocol checks are enumerated in the project operator and E2E checklists. Site-specific addresses and profiles should be supplied through private canonical configuration, never embedded in the release artifact or this report.

## Source Documents

- [Architecture](./ARCHITECTURE.md)
- [Configuration and reconciliation](./CONFIGURATION.md)
- [Deployment overview](./DEPLOYMENT_OVERVIEW.md)
- [Upgrade and rollback](./UPGRADE_AND_ROLLBACK.md)
- [Operator checklist](./OPERATOR_CHECKLIST.md)
- [Manual E2E checklist](./MANUAL_E2E_TEST_CHECKLIST.md)

The site-specific acceptance record remains private operational evidence and is intentionally not part of the public repository.
