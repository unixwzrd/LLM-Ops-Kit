# Changelog

## Unreleased

### Beta release readiness

- Added a reconciled product-release manifest with explicit component bindings, real managed-product versions, latest-release metadata, update disposition, and `llmops product list/show` inspection.
- Unified the default CLI and TUI status columns through one shared presentation contract while keeping toolkit/runtime identity separate from managed-product versions.
- Excluded externally owned tool and service components from stack lifecycle plans while retaining them in stack status; direct lifecycle mutations remain read-only.
- Changed the media-history template to remove every textual image tool call/result pair, including the most recent truncated result, while preserving native structured vision requests and their Qwen vision placeholders.
- Added canonical configuration schema version 2 with versioned JSON Schema 2020-12 service templates, constrained UI metadata, one-time v1 migration, and no runtime v1 compatibility reads.
- Added built-in templates for llama.cpp, generic non-llama modelctl workloads, model-proxy, tts-bridge, standalone processes, user and external launchd, SSH tunnels, generic agents, external HTTP services, RTK, and experimental user systemd.
- Made schema-v2 migration normalize real proof-of-concept `env` profiles, string service ports, native-MTP llama settings, non-llama TTS modelctl profiles, external agents, and launchd-owned tunnels without deleting source fields.
- Allowed reconciliation to replace a selected version-one snapshot during the bounded schema-v2 cutover while retaining strict version-two-only runtime reads and target-side validation before selection.
- Prevented local-target reconciliation probes from inheriting authority-tree path overrides and comparing the mutable authority hash to the selected role-filtered snapshot.
- Kept Textual desired-state reloads bound to the explicitly selected configuration root and added headless acceptance that creates a complete disabled component/profile through generated forms without manual JSON.
- Added schema-aware template, profile, and component inspection, typed multi-field `--set` and `--unset`, transactional profile creation/editing/cloning, component add/clone/retire/restore, stale-authority-hash refusal, and endpoint-derived dependencies.
- Added a Textual Service Catalog, generated profile forms, full component Details, stack membership/dependency inspection, dynamic host/profile/endpoint choices, and llama.cpp speculation conflict handling.
- Added one designated desired-state authority to the observer catalog. Schema mutations invoked on another trusted host are forwarded to the authority, and `llmops tui` launched on a trusted peer runs on the authority through SSH.
- Added RTK as a non-service tool template with version, telemetry, verification, gain, and Hermes dry-run actions. Live evidence confirms telemetry disabled and leaves hook installation behind an explicit canary approval gate.
- Replaced inherited Textual accent states with one explicit blue-gray high-contrast palette across Settings, forms, select overlays, buttons, cursors, and scrollbars.
- Styled condition, lifecycle, health, component version, and drift independently in CLI and TUI status so healthy processes remain visibly healthy while stale-runtime and other attention conditions stay visible.
- Prevented delayed main-table highlight events from updating a detail widget behind an active configuration or catalog modal, and suppressed the routine SSH closure banner for authority-routed TUI sessions.
- Made topology filters apply immediately, replaced Apply with Reset, restored semantic host/component colors, exposed Settings in the primary action bar, and made the visible Quit button exit directly.
- Moved the TUI's clickable lifecycle action bar above the component table so primary controls remain immediately accessible.
- Made a newer controller reselect a complete target retained as an older peer's `previous` release, allowing coordinated return after rollback without relying on the old peer's update implementation.
- Prevented failed duplicate-release installation from deleting the pre-existing immutable release directory through its cleanup trap.
- Made selected-host rollback honor `--host` and `--all-hosts`, skip peers already at the target release, and reselect a complete target already present as `previous` instead of reinstalling or deleting it during failure recovery.
- Persisted the immutable runtime that launched each model process and made runtime provenance prefer that start marker over a newer selected wrapper.
- Pruned historical assistant tool calls that explicitly decode or save prior base64 media even when the copied bytes are referenced through a temporary file rather than embedded in the call itself.
- Corrected configuration reconciliation and TUI configuration editing to consume the mutable authority tree rather than regenerating desired snapshots from the active deployed revision.
- Replaced the custom latest-image template with a structurally detected media-history template that removes textual image tool results and assistant-side base64 copies while leaving native structured multimodal content intact. The stock Qwen template remains unchanged.
- Added `llmops config effective`, host-qualified component log channels, component runtime/version inspection, configurable lifecycle timeouts, and persisted detached operation records.
- Added desired-versus-observed runtime reporting and stale-runtime detection based on live process commands and immutable release identities.
- Made long-running TUI lifecycle and toolkit update actions continue through detached short-lived workers so exiting the TUI neither cancels nor waits for active work.
- Added operation progress states, mouse-accessible actions, Escape-safe modals, populated topology filters, lower-intensity accessible colors, and explicit log host/channel display.
- Replaced the ambiguous status field with independent lifecycle, health, condition, and observability fields, plus distinct toolkit and observed component versions.
- Added the configured component execution identity as `execution_user` in JSON and `RUN_AS` in CLI and TUI status, distinguishing service ownership from the operator invoking LLM-Ops-Kit.
- Persisted operator-requested lifecycle state so an intentional stop reports `lifecycle=stopped`, `desired_lifecycle=stopped`, and `condition=down` instead of a false error; unexpectedly stopped components remain errors.
- Corrected model-proxy observation so a live proxy with an unavailable upstream is reported as running and degraded rather than stopped.
- Centralized component mutation preparation so CLI and Textual operations enforce the same active-dependent stop policy.
- Added immediate keyboard-driven detail updates, selection preservation, high-contrast status styling, contextual help, local automatic-refresh settings, and shared organization/site labels to the Textual console.
- Added bounded host-grouped topology projections with table, JSON, Mermaid, and DOT CLI output and a filterable collapsible Textual view.
- Added optional adapter update and relocation capability contracts without enabling unsafe generic mutation behavior.
- Packaged the control library in a conventional `src/llmops_kit` layout with one authoritative version, console entry point, locked dependencies, built-in resources, and optional Textual dependency metadata.
- Added a checksummed release wheelhouse containing the project, Jinja2, Textual, and transitive dependencies for offline installation.
- Made the release builder consume commit metadata exported into `RELEASE.json`, allowing the public artifact to be built directly from `git archive` without reconstructing a Git checkout.
- Reworked installation around one UV-managed Python runtime and one application environment per immutable release; installed commands no longer depend on system Python, Conda activation, virtual environments, or shell startup files.
- Added normal and `--minimal` installation, repair, local and coordinated host update, installer-level rollback, default uninstall, and purge behavior.
- Added a versioned adapter registry, built-in adapter manifests, adapter discovery through Python entry points, `llmops adapter` commands, and conformance tests.
- Added the on-demand `llmops tui` operations console with status, lifecycle plans, logs, deterministic validation, guided existing-component configuration, explicit confirmation, and equivalent CLI commands.
- Added runtime version, catalog/configuration hashes, authority, drift, and synchronization metadata to status records.
- Made the CLI and Textual TUI use one catalog-aware status collector so intentionally peer-unobservable components consistently report `authority-only` rather than `unreachable`.
- Made maintainer precheck load the release-candidate source tree explicitly, preventing an older installed package from satisfying or breaking source regressions.
- Made trusted control-host snapshots carry the complete secret-free topology while component-only hosts remain role-filtered, allowing dependency-aware lifecycle operations from either trusted host.
- Made aggregate peer status constrain each remote observation to that peer's owned components, preventing duplicate observations when trusted hosts share the complete topology.
- Made model-proxy prefer the application-owned Python interpreter when no service-specific interpreter is configured, including clean-archive render operation.
- Added `llmops --version` for direct installed-runtime verification.
- Made every installed runtime wrapper select the same managed `current-config` revision as the public `llmops` command, including cross-host model lifecycle operations.
- Made every SSH transport use the inventory `control_host` when present, preventing peer operations from resolving a remote host's local service address such as `localhost` on the wrong machine.
- Added transactionally verified role-filtered configuration revisions, `llmops config hash`, and `llmops config reconcile`; manual target drift blocks replacement and is never merged automatically.
- Added coordinated remote update preflight, artifact staging, older-peer use, missing-peer bootstrap, sequential apply, post-update version/configuration verification, and rollback of hosts changed by a failed invocation.
- Added dual-architecture macOS wheelhouses for Apple Silicon and Intel, plus custom-prefix install metadata so guided initialization and probes use the actual application layout.
- Added an explicit macOS platform gate so experimental Linux runs stop before selecting or downloading an incompatible Apple runtime.
- Restricted release extraction to data-safe tar members for repository-free distribution and remote updates.
- Removed UV's generated wheelhouse ignore file from runtime archives.
- Made the installed launcher select the active immutable configuration revision by default while preserving an explicit configuration override.
- Added a bounded first-beta rollback path that restores a prior immutable script runtime and can return to the application-owned beta release.
- Made configuration reconciliation preserve drift details returned with nonzero status, refuse unreachable/error targets, retain immutable revisions, and record the previous configuration link before atomic replacement.
- Retired the proof-of-concept source-checkout deployment and stage/drift implementation in favor of repository-free updates and independent desired-state reconciliation.
- Added operator, TUI, adapter, remote-operation, installation, upgrade, rollback, and recovery documentation.
- Added a publication-ready engineering evidence report with architecture invariants, acceptance evidence, and Mermaid diagrams for topology, coordinated updates, immutable rollback, reverse dependency shutdown, and configuration reconciliation.

### Product direction

- Defined LLM-Ops-Kit as an extensible, lightweight AI subsystem control plane rather than a container scheduler, model engine, or agent.
- Specified clean module boundaries for configuration, schemas, topology, planning, execution, adapters, transports, deployment, observability, and operator interfaces.
- Defined a versioned adapter manifest and capability model so launchd, systemd, standalone processes, SSH, model engines, agents, memory systems, optimization tools, and observability providers can be added without modifying the control core.
- Established `llmops` as the canonical public command representation while requiring CLI, Textual TUI, optional WebUI, and future agent skills to consume the same operation model and display equivalent commands.
- Added a one-week beta roadmap centered on a UV-owned runtime, Textual control panel, existing llama.cpp stack, model-proxy observability, and two-user macOS acceptance.
- Audited the existing Secrets-Kit bootstrap and release workflow for reuse. Adopted its UV discovery/bootstrap, versioned runtime, wheel, state, repair/upgrade, artifact, and multi-host acceptance patterns while explicitly excluding product-specific initialization and embedded Python shell blocks.
- Defined staged reuse of MLXForge's static FastAPI WebUI patterns and visual/widget contracts without introducing a repository dependency or prematurely extracting a shared package.
- Recorded completion of the 48-hour runtime soak and regenerated two source-date operational reports from 48 hourly archived records without hiding the migration and cold-cycle exceptions.
- Kept systemd/Linux, MLXForge, Mnemosyne, RTK, Headroom, optional WebUI, and external TTS providers behind explicit staged acceptance gates.

## Operator V1 Release Candidate

### Configuration and migration

- Replaced proof-of-concept shell configuration with canonical JSON profiles, inventories, services, and dependency-aware stacks.
- Added transactional guided initialization with selective reuse and normalization of existing model profiles.
- Added classified one-way migration for legacy model, service, agent, and inventory inputs without retaining runtime compatibility reads.
- Added read-only host probing for SSH, executables, Python, model paths, launchd, ports, architecture, and memory.

### Lifecycle and multi-host operation

- Added independent component lifecycle operations and dependency-aware stack composition with non-mutating plans, readiness checks, idempotence, cascade behavior, and partial-start rollback.
- Added the proof-of-concept immutable multi-host deployment that established the role-filtered configuration and topology contracts later replaced by beta update and reconciliation commands.
- Added aggregate `llmops status`, trusted peer host operations over SSH, absolute remote command paths, and explicit `authority-only` status for components intentionally observable only from the desired-state authority.
- Added component help descriptions and agent-neutral profiles without privileged Hermes or OpenClaw behavior.

### Installation and updates

- Added a runtime-only `.tar.xz` release artifact with a per-file manifest and external SHA-256 checksum.
- Added a separately checksummed bootstrap installer for repository-free installation.
- Added `llmops update` check, plan, JSON, verified local apply, and offline artifact workflows.
- Added clean-archive fresh-install, upgrade, repair, rollback, uninstall, purge, migration, privacy, documentation, and macOS release checks.
- Excluded tests, migration fixtures, private topology, and maintainer-only release tooling from installed runtime payloads.
- Made maintainer prechecks use the environment-selected `python`, report its resolved path and version, reject interpreters outside an active Conda or virtualenv prefix, and honor `PYTHON_BIN` as an explicit override.

### Models, proxy, and logging

- Centralized model log rotation using copy-and-truncate so active log paths and inodes remain stable for monitoring tools.
- Kept model-proxy strictly passive: diagnostic prompt rendering never changes the request forwarded upstream.
- Added Hugging Face-compatible `raise_exception` support to model-proxy chat-template rendering, with regressions against the shipped Qwen template.
- Added an optional Qwen template derived from the unchanged stock template that prunes textual image tool responses while preserving native structured multimodal inputs.
- Added focused regressions for historical tool exchanges, duplicate embedded payloads, and structured image and video content.

### Cleanup and documentation

- Removed repository synchronization, post-commit synchronization, ignored runtime wrappers, embedded Python in shell scripts, private machine defaults, and obsolete internal procedures.
- Replaced generated ignore rules with a project-specific `.gitignore` and removed repository-local staging and temporary artifacts.
- Rewrote operator documentation for the final `llmops` command surface, clean installation, migration, configuration, proxy diagnostics, upgrades, rollback, and uninstall.

## Pre-release History

Earlier commits document the exploratory model runners, proxy tap, TTS bridge, and deployment experiments that led to operator v1. Those proof-of-concept interfaces are not supported by this release.
