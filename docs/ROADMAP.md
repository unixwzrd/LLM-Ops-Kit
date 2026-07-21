# Roadmap

**Created**: 2026-07-19
**Updated**: 2026-07-21

Back: [Documentation index](./INDEX.md)

## Direction

LLM-Ops-Kit will become an extensible, local-first control plane for operating AI subsystems across one host, a trusted LAN, VPS instances, and existing container environments. It coordinates native services rather than replacing launchd, systemd, SSH, Docker, Kubernetes, model engines, or agents.

## Beta Target: 2026-07-26

The beta is deliberately narrow. It should make the existing operator-v1 capabilities installable and understandable without expanding into autonomous remediation or a general infrastructure platform.

### Release blockers

1. Complete final-artifact install, minimal install, repair, upgrade, rollback, uninstall, and purge acceptance on the ARM and Intel macOS test users.
2. Complete coordinated two-host update, old-peer bootstrap, failure rollback, configuration reconciliation, and conflict-refusal acceptance.
3. Repeat live-host upgrade and global-status validation without restarting unaffected services.
4. Reconcile current documentation and produce a clean committed archive with release-hygiene evidence.
5. Obtain a green macOS CI run and close the standardized operational-report evidence gap before publication.

The application-owned UV runtime, standard Python package, dual-architecture offline wheelhouse, adapter registry, core Textual dashboard, version/drift status, remote update implementation, and configuration reconciliation implementation are complete and covered by local regression tests. They remain release candidates until the final host acceptance sequence passes.

The runtime completed its 48-hour soak with continuous successful hourly health checks. Scheduler defects discovered during the window were repaired and their jobs rerun successfully. Installer and TUI development may proceed; publication still requires the missing standardized daily report artifacts or an explicit replacement acceptance record.

### Beta TUI

- Overview of hosts, components, stacks, lifecycle, health, condition, observability, versions, and drift.
- High-contrast keyboard and mouse navigation, automatic-refresh settings, shared display labels, contextual help, and recent logs.
- Component and stack start, stop, restart, plan, and explicitly toolkit-scoped update-check actions.
- Equivalent `llmops` command shown before mutation.
- Guided editing for stable existing-component fields, dependencies, ownership, and readiness timeout.
- Read-only bounded topology grouped by host with host, stack, driver, and condition filters.
- No daemon, autonomous changes, model downloads, or secret-value editor.

The TUI should begin as a compact operational dashboard. Configuration screens are reached from host or component detail views rather than presenting every possible field at startup.

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
- Product-native update providers enabled only after backup, rollback, and post-update health acceptance.
- Stateless component relocation for proxies, bridges, dashboards, and tunnels with preflight, transactional cutover, and rollback.
- Typed early-alpha MLXForge engine adapter behind an explicit feature flag.
- TTS Bridge recipe for OpenAI-compatible local or remote speech services; providers and voice material remain user supplied.

## Integration Catalog

The following are adapter or recipe candidates, not core dependencies:

| Integration | Intended capability | Release position |
|---|---|---|
| Hermes Agent | Generic service profile plus optional guided recipe | Beta fixture |
| OpenClaw | Generic service profile plus optional guided recipe | Post-beta |
| Mnemosyne | Install/configure/health/update recipe for supported agents | Nice-to-have V1 |
| RTK | Install, telemetry check, agent plugin canary, gain metrics, and rollback | Nice-to-have V1 |
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
