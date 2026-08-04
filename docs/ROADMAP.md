# Roadmap

**Created**: 2026-07-19
**Updated**: 2026-07-23

Back: [Documentation index](./INDEX.md)

## Direction

LLM-Ops-Kit will become an extensible, local-first control plane for operating AI subsystems across one host, a trusted LAN, VPS instances, and existing container environments. It coordinates native services rather than replacing launchd, systemd, SSH, Docker, Kubernetes, model engines, or agents.

## Beta Target: 2026-07-26

The beta is deliberately narrow. It should make the existing operator-v1 capabilities installable and understandable without expanding into autonomous remediation or a general infrastructure platform.

### Release blockers

1. Replay authoritative Hermes image-generation and dedicated vision requests through the revised media-history template, proving textual tool-result images are removed while native structured vision input remains bound through one Qwen vision placeholder.
2. Complete final-artifact install, minimal install, repair, upgrade, rollback, uninstall, and purge acceptance on the ARM and Intel macOS test users.
3. Complete coordinated two-host update, old-peer bootstrap, failure rollback, configuration reconciliation, and conflict-refusal acceptance.
4. Upgrade both live hosts, reconcile the revised Qwen/model-proxy profiles, and repeat protocol and global-status validation without restarting unaffected services.
5. Produce a clean committed archive with release-hygiene evidence, obtain explicit approval, and require green macOS CI before publication.

The application-owned UV runtime, standard Python package, dual-architecture offline wheelhouse, adapter registry, core Textual dashboard, version/drift status, remote update implementation, and configuration reconciliation implementation are complete and covered by local regression tests. They remain release candidates until the final host acceptance sequence passes.

Canonical configuration schema version 2, reviewed service templates, typed CLI mutation, generated Textual forms, reusable profile management, endpoint wiring, reversible component retirement, and authority-routed edits are implemented. Fresh operators can create a topology through the CLI or Service Catalog without hand-editing JSON. RTK inspection is implemented as a tool component; the mutating Hermes canary remains an explicit acceptance gate.

The runtime completed its 48-hour soak with continuous successful hourly health checks. Scheduler defects discovered during the window were repaired and their jobs rerun successfully. Installer and TUI development may proceed; publication still requires the missing standardized daily report artifacts or an explicit replacement acceptance record.

### Beta TUI

- Overview of hosts, components, stacks, lifecycle, health, condition, observability, versions, and drift.
- High-contrast keyboard and mouse navigation, automatic-refresh settings, shared display labels, contextual help, and recent logs.
- Component and stack start, stop, restart, plan, and explicitly toolkit-scoped update-check actions.
- Equivalent `llmops` command shown before mutation.
- Schema-generated service creation and editing for reviewed templates, reusable profiles, endpoint connections, dependencies, ownership, and readiness timeouts.
- Read-only bounded topology grouped by host with host, stack, driver, and condition filters.
- No daemon, autonomous changes, model downloads, or secret-value editor.
- Detached short-lived workers persist accepted long-running operations and survive TUI exit without creating a resident privileged service.

The TUI should begin as a compact operational dashboard. Configuration screens are reached from host or component detail views rather than presenting every possible field at startup.

### Prioritized Operator Polish

1. **P0 - TUI interaction correctness:** Keep the visible Quit action equivalent to `q`, expose Settings in the primary action bar, apply topology filters immediately, provide one Reset action, and retain semantic condition colors in topology groups and components.
2. **P1 - Remote log operations:** Add CLI list/read/follow operations for every adapter-declared log channel, resolving host and execution user through the catalog. Add a full-screen scrollable TUI viewer with channel selection, host/path identity, refresh, and follow controls.
3. **P1 - Guided discovery:** Build optional host, executable, and port discovery over the completed four-step schema-driven creation flow. Fresh users can create validated profiles and disabled components, wire required endpoints, and import reviewed local templates without manual JSON editing.
4. **P1 - Template refinement:** Continue expanding reviewed product-specific labels, help, units, grouping, constraints, and dynamic option providers using the shared JSON Schema contract. The same schemas serve CLI, TUI, future WebUI, recipes, and third-party adapters.
5. **P2 - Lifecycle ownership and restart policy:** Model standalone, manual, launchd, and later systemd ownership explicitly. Separate crash recovery from an operator-requested stop, and expose install/remove/enable/disable plus bounded restart policy without adding a privileged daemon.
6. **P2 - Stack and host management:** Distinguish catalog host aliases from network hostnames, add full-screen stack membership and dependency views, support stack creation/editing and logical grouping, and keep desired-state reassignment separate from provisioning or stateful relocation.

### Shared UX

The optional WebUI should reuse the proven MLXForge pattern: a separate FastAPI process, static HTML/CSS/JavaScript, structured JSON errors, SSE for lifecycle events, and availability independent of model processes. Reuse visual tokens and widget contracts initially; extract a shared package only after both products demonstrate a stable common implementation.

### Beta adapters

- launchd
- Standalone managed process
- SSH and SSH tunnel
- llama.cpp through the existing model lifecycle
- model-proxy
- tts-bridge
- Generic agent process/service profiles

macOS remains the supported beta platform. A systemd adapter may be developed and exercised against Debian and Rocky Linux fixtures during the beta, but Linux support is not declared until clean install, lifecycle, upgrade, rollback, and uninstall acceptance passes on both distributions.

## V1

- Stable public adapter API with compatibility checks and entry-point discovery.
- Signed or otherwise authenticated adapter/catalog metadata.
- systemd and constrained container-endpoint adapters after Linux acceptance.
- Optional loopback WebUI using static assets and the shared control API.
- Rule-based health and drift remediation suggestions with explicit plans and approval.
- Agent-neutral operational skill for read-only status, doctor, plan, drift, and approved lifecycle actions.
- Component update catalog with security/benefit/risk summaries and rollback metadata.
- Authority-owned append-only installation history for bundled stack components, with artifact identity, validation evidence, and rollback locators available from component details and CLI history inspection.
- Product-native update providers enabled only after backup, rollback, and post-update health acceptance.
- Stateless component relocation for proxies, bridges, dashboards, and tunnels with preflight, transactional cutover, and rollback.
- Typed early-alpha MLXForge engine adapter behind an explicit feature flag.
- Resume MLXForge only after its accepted Q3 Phase A correction is reviewed and committed. Its first adapter contract is limited to version, health, lifecycle, OpenAI-compatible endpoints, model operations, configuration, and logs.
- Resume Secrets-Kit from a fresh read-only blocker audit and its highest authorized blocker. Integrate later only through opaque provider references after standalone lifecycle and rollback acceptance.
- TTS Bridge recipe for OpenAI-compatible local or remote speech services; providers and voice material remain user supplied.

## Integration Catalog

The following are adapter or recipe candidates, not core dependencies:

| Integration | Intended capability | Release position |
|---|---|---|
| Hermes Agent | Generic service profile plus optional guided recipe | Beta fixture |
| OpenClaw | Generic service profile plus optional guided recipe | Post-beta |
| Mnemosyne | Install/configure/health/update recipe for supported agents | Nice-to-have V1 |
| RTK | Tool status, telemetry check, verification, gain, and Hermes dry-run are implemented; enable and rollback await canary approval | Beta gated |
| Headroom | Install, health, metrics, routing canary, and rollback | Nice-to-have V1 |
| MLXForge | Model engine lifecycle and health | Early-alpha V1 |
| mlx-audio | External OpenAI-compatible TTS endpoint through TTS Bridge | Community/experimental |
| ElevenLabs | External TTS endpoint and operator-defined aliases through TTS Bridge | Experimental after provider testing |

## Later

- HTTPS control endpoint with explicit authentication and authorization.
- Community adapter SDK, template, conformance tests, compatibility matrix, and publishing workflow.
- Multiple desired-state authorities only if a clear conflict-resolution model is designed; no implicit distributed merge.
- Additional cloud, VPS, container, model-engine, memory, cache, and observability adapters driven by tested demand.
- Stateful relocation only after adapters declare data ownership, transfer, integrity validation, and rollback behavior.

## Explicit Non-Goals

- Scheduling workloads like Kubernetes.
- Building or managing virtual machines and containers.
- Replacing model engines, agents, secret stores, or observability platforms.
- Autonomous AI remediation.
- Shipping model weights, voice samples, private topology, or credentials.
- Installing every available integration by default.
