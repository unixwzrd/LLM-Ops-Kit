# Maintainer TODO

**Created**: 2026-07-16
**Updated**: 2026-08-07

Back: [Documentation index](./INDEX.md)

## Completed Beta Implementation

- [x] Package the control library in a conventional `src/llmops_kit` layout with a locked UV project, console entry point, package resources, and one authoritative version.
- [x] Build a checksummed release archive with an offline Apple Silicon and Intel macOS wheelhouse.
- [x] Bootstrap checksum-verified UV and managed Python without Git, system Python, Conda, a source checkout, or shell-profile activation.
- [x] Support normal Textual and `--minimal` CLI installations, repair, immutable current/previous releases, local update, rollback, normal uninstall, and purge.
- [x] Preserve configuration and operational state outside immutable releases and record the actual custom install layout for initialization and probes.
- [x] Register built-in lifecycle adapters through a versioned entry-point registry and provide `adapter list`, `adapter show`, `adapter doctor`, and conformance fixtures.
- [x] Replace ambiguous status with shared lifecycle, health, condition, observability, component-version, and toolkit-version fields across CLI and TUI.
- [x] Add coordinated remote update selection, preflight, staging, old-peer use, missing-peer bootstrap, sequential apply, post-apply identity verification, and rollback reporting.
- [x] Add one-way configuration reconciliation with complete trusted-controller snapshots, role-filtered component-host snapshots, conflict refusal, immutable revisions, previous/current links, and no automatic merge.
- [x] Add the on-demand high-contrast Textual dashboard with immediate keyboard detail updates, refresh settings, help, shared display labels, bounded topology, logs, plans, lifecycle actions, dependent-impact confirmation, existing-component editing, and equivalent CLI commands.
- [x] Remove proof-of-concept repository synchronization, source-checkout deployment, runtime legacy reads, embedded Python shell blocks, and privileged Hermes/OpenClaw behavior.
- [x] Preserve test-only legacy migration fixtures; they are not installed in release artifacts.
- [x] Complete the prior operator-v1 48-hour live soak while retaining prior runtimes and checksummed backups.
- [x] Add the media-history template, pruning textual image tool results and duplicate assistant-side copies while preserving native structured vision requests and leaving proxy transport bytes unchanged.
- [x] Add effective configuration, host-qualified log channels, component runtime/version inspection, lifecycle timeouts, and persistent detached operation inspection.
- [x] Make TUI lifecycle/update actions non-blocking and add progress states, Escape-safe modals, clickable actions, populated topology filters, and accessible colors.
- [x] Add canonical schema version 2, reviewed JSON Schema service templates, typed field inspection and mutation, transactional profile/component creation, endpoint wiring, reversible retirement, and stale-authority-hash refusal.
- [x] Add the Textual Service Catalog, generated profile forms, full Details, stack membership/dependency inspection, and dynamic host/profile/endpoint choices.
- [x] Route schema operations and the Textual console from trusted peers to one designated desired-state authority.
- [x] Add RTK as a tool component with installation status, version, telemetry, verification, gain, and Hermes integration dry-run actions.
- [x] Separate managed-product releases from toolkit runtime identity with a reconciled product manifest, shared CLI/TUI status columns, update metadata, and public inventory inspection.
- [x] Add catalog-wide template-declared component log listing, bounded reads, JSON output, interrupt-safe CLI follow, and a full-screen remote-aware TUI log viewer.
- [x] Make managed launchd lifecycle symmetric so start and restart bootstrap an unloaded configured plist before kickstart while stop remains idempotent.

## Beta Release Gates

- [x] Replay historical Hermes image-generation context through the installed media-history template and confirm textual tool-result image payloads and duplicate assistant base64 copies are removed.
- [x] Capture a dedicated Hermes vision request and confirm its raw request retains the structured `image_url` while the rendered prompt contains one Qwen vision placeholder. The two captured upstream requests reached the model and returned `500 Compute error`, which is an upstream vision execution issue rather than Jinja image removal.
- [x] Pass the dependency-complete source suite and precheck in the packaged UV environment. Source candidate `0.9.0b22` passes precheck on 2026-07-23, including the dedicated-vision-after-tool-history regression.
- [x] Pass normal clean installation from a verified archive on isolated Apple Silicon and Intel macOS users.
- [x] Repeat normal installation from committed release artifacts on both macOS users after schema and reconciliation fixes; Apple Silicon and Intel installs include the application-owned Python, Textual, JSON Schema, and all built-in templates.
- [x] Pass `--minimal` installation on isolated Apple Silicon and Intel macOS users and confirm the CLI works while `llmops tui` reports the omitted optional dependency cleanly.
- [x] Pass guided interactive model-profile reuse and deterministic non-interactive import against each test user's existing model profiles.
- [ ] Pass final-artifact repair, upgrade, rollback, normal uninstall, and purge on both macOS users.
- [x] Pass final-artifact Textual interaction tests for status, arrow and mouse selection, selection persistence, automatic-refresh pause, help, settings, topology, lifecycle impact confirmation/cancellation, configuration validation, update check, and update cancellation. Six TUI and 42 control-plane tests passed against the installed beta wheel with repository source removed from `PYTHONPATH`.
- [x] Pass coordinated two-host update tests for unreachable preflight, interrupted transfer, old-peer bootstrap, apply failure, automatic rollback, and mixed-version refusal.
- [x] Pass live configuration reconciliation plan/apply/idempotence and independently edited target conflict refusal.
- [x] Confirm identical topology/catalog hashes and global status from both trusted live hosts.
- [x] Upgrade both live hosts through `0.9.0b16`, reconcile template/profile changes, validate services, roll back once, and return to the candidate. Live acceptance exposed and corrected ignored remote rollback selection, unsafe duplicate-install cleanup, and old-peer return behavior before the coordinated b14 to b13 to b14 cycle passed; the UI-only b15 and b16 updates then passed on both hosts without restarting the intentionally stopped chat model.
- [ ] Re-run model, embedding, TTS, model-proxy, tts-bridge, gateway, dashboard, tunnel, dependency, cascade, individual restart, and cold-start acceptance against the final artifact. The `0.9.0b4` baseline passed; the documentation-and-test revision still requires final-artifact repetition.
- [x] Produce clean local release commits and build exclusively from committed source; precheck covers documentation links, secret/private-path scans, archive content, and ignored-file audits. The operator's pre-existing `.gitignore` edit remains intentionally outside the release commits.
- [x] Regenerate the two missing standardized operational reports from 48 hourly archived source records. The reports preserve transient migration and cold-cycle exceptions rather than describing the cycles as uninterrupted steady state.
- [x] Run non-blocking installer experiments on Debian and Rocky. Both stop before mutation with the documented macOS-only beta error; Linux support is not claimed.
- [ ] Obtain explicit user approval before push or tag, then require green macOS CI and publish a GitHub prerelease with checksums, manifest, changelog, upgrade, and rollback instructions.

## Deferred From Beta

- [x] Add catalog-wide component log list/read/follow operations and a full-screen scrollable TUI viewer with template-declared channels, remote host/user resolution, path identity, refresh, and follow controls.
- [ ] Extend guided initialization with optional host and executable discovery. Fresh topology creation is now available through templates in the CLI and TUI without manual JSON editing.
- [x] Replace the single Add Component modal with a four-step placement, settings, connections, and review flow; add grouped editing, advanced disclosure, reset/revert controls, and reviewed local-template import.
- [ ] Expand schema coverage for product-specific fields discovered during beta operation; unknown extension fields remain preserved and available through advanced CLI file input.
- [ ] Add explicit manual/standalone/launchd lifecycle ownership and crash-only restart policies that never override an intentional operator stop.
- [x] Make managed launchd lifecycle symmetric and prove stop, start, loaded restart, and unloaded restart against an isolated launchctl fixture. Final live validation remains part of the scheduled artifact acceptance window.
- [ ] Add mutating stack creation and membership editing. Full-screen membership, dependencies, and connection inspection are complete.
- [ ] Add deterministic corrective suggestions from active probes to the TUI. The beta TUI shows configuration validation only.
- [ ] Add a correlated model-proxy diagnostic exchange browser. The beta exposes component logs without modifying proxy traffic.
- [ ] Package an agent-neutral operational skill using `doctor`, `plan`, `status`, and JSON output with explicit approval for mutations and SSH provisioning.
- [ ] Add adapter-owned recovery policies with desired-running state, bounded retry/backoff, network-availability gating, restart count, last-exit status, and last-successful-recovery evidence. Keep automatic restart disabled by default except for explicitly supervised transports such as SSH tunnels.
- [ ] Add a network-outage acceptance fixture covering tunnel loss, launchd restart, endpoint recovery, status convergence, and client reconnection. Treat Desktop session reconnection as a client capability rather than proof that the tunnel failed.
- [ ] Add the loopback static WebUI over the same control library after the TUI stabilizes.
- [ ] Add stateless component relocation with adapter preflight, cutover, dependent endpoint update, and rollback. Do not treat a desired-state host edit as provisioning.
- [ ] Add component-native update check/plan/apply commands after provider backup, rollback, and post-update health contracts pass acceptance.
- [x] Add a validated authority-owned append-only product installation ledger to the reconciled manifest, retain it on trusted control snapshots, and expose it through product details and `llmops product history` without expanding the default status table.
- [ ] Append installation history automatically from component-native update and rollback operations after their provider contracts pass acceptance.
- [ ] Run the bounded Hermes RTK canary after explicit approval, capture owned-file backups, compare diagnostics and token reduction, and prove disable/rollback before retaining the hook.

## Integration Roadmap

- [ ] Add an early-alpha MLXForge engine adapter after inference and lifecycle contracts stabilize.
- [ ] Review and commit MLXForge's accepted Q3 Phase A correction before authorizing further qualification or adapter implementation.
- [ ] Perform a fresh read-only Secrets-Kit blocker audit, then resume only its highest authorized blocker under existing review gates.
- [ ] Add systemd and complete Debian/Rocky acceptance before declaring Linux support.
- [ ] Add optional recipes for Hermes, OpenClaw, Mnemosyne, RTK, and Headroom without making them core dependencies.
- [ ] Add a TTS Bridge provider contract for operator-supplied local or remote OpenAI-compatible speech endpoints; never ship voices or credentials.
- [ ] Integrate Secrets-Kit through opaque provider references after its standalone release and rollback contracts stabilize, then retire plaintext `.env` injection.
- [ ] Publish an adapter SDK with a template, manifest schema, compatibility policy, conformance suite, test doubles, and uninstall contract.
- [ ] Add authenticated adapter catalog metadata before third-party installation is supported.
