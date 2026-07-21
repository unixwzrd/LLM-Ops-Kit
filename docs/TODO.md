# Maintainer TODO

**Created**: 2026-07-16
**Updated**: 2026-07-21

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
- [x] Add the media-history template, preserving one final image-bearing tool response while pruning earlier payloads and duplicate assistant-side copies without changing proxy transport bytes.
- [x] Add effective configuration, host-qualified log channels, component runtime/version inspection, lifecycle timeouts, and persistent detached operation inspection.
- [x] Make TUI lifecycle/update actions non-blocking and add progress states, Escape-safe modals, clickable actions, populated topology filters, and accessible colors.

## Beta Release Gates

- [x] Replay the current Hermes request through the installed media-history template and confirm one final historical image-bearing tool response, no earlier payloads, and no duplicate assistant base64 copies. The installed `0.9.0b14` replay retained one image result and one PNG marker, with zero assistant decode/copy calls.
- [x] Pass the dependency-complete source suite and precheck in the packaged UV environment. Commit `4640ae8` passed 146 tests and precheck on 2026-07-21.
- [x] Pass normal clean installation from a verified archive on isolated Apple Silicon and Intel macOS users.
- [ ] Repeat normal installation from the final committed release artifact on both macOS users after documentation and acceptance fixes stop changing the package.
- [x] Pass `--minimal` installation on isolated Apple Silicon and Intel macOS users and confirm the CLI works while `llmops tui` reports the omitted optional dependency cleanly.
- [x] Pass guided interactive model-profile reuse and deterministic non-interactive import against each test user's existing model profiles.
- [ ] Pass final-artifact repair, upgrade, rollback, normal uninstall, and purge on both macOS users.
- [x] Pass final-artifact Textual interaction tests for status, arrow and mouse selection, selection persistence, automatic-refresh pause, help, settings, topology, lifecycle impact confirmation/cancellation, configuration validation, update check, and update cancellation. Six TUI and 42 control-plane tests passed against the installed beta wheel with repository source removed from `PYTHONPATH`.
- [ ] Pass coordinated two-host update tests for unreachable preflight, interrupted transfer, old-peer bootstrap, apply failure, automatic rollback, and mixed-version refusal.
- [x] Pass live configuration reconciliation plan/apply/idempotence and independently edited target conflict refusal.
- [x] Confirm identical topology/catalog hashes and global status from both trusted live hosts.
- [x] Upgrade both live hosts through `0.9.0b15`, reconcile template/profile changes, validate services, roll back once, and return to the candidate. Live acceptance exposed and corrected ignored remote rollback selection, unsafe duplicate-install cleanup, and old-peer return behavior before the coordinated b14 to b13 to b14 cycle passed; the UI-only b15 update then passed on both hosts.
- [ ] Re-run model, embedding, TTS, model-proxy, tts-bridge, gateway, dashboard, tunnel, dependency, cascade, individual restart, and cold-start acceptance against the final artifact. The `0.9.0b4` baseline passed; the documentation-and-test revision still requires final-artifact repetition.
- [ ] Produce a clean local release commit and build exclusively from `git archive HEAD`; require clean status, documentation links, secret scan, private-path scan, archive audit, and ignored-file audit.
- [x] Regenerate the two missing standardized operational reports from 48 hourly archived source records. The reports preserve transient migration and cold-cycle exceptions rather than describing the cycles as uninterrupted steady state.
- [x] Run non-blocking installer experiments on Debian and Rocky. Both stop before mutation with the documented macOS-only beta error; Linux support is not claimed.
- [ ] Obtain explicit user approval before push or tag, then require green macOS CI and publish a GitHub prerelease with checksums, manifest, changelog, upgrade, and rollback instructions.

## Deferred From Beta

- [ ] Add catalog-wide `component logs list/read/follow` commands and a full-screen scrollable TUI log viewer with adapter-declared channels, remote host/user resolution, path identity, refresh, and follow controls.
- [ ] Add an adapter-driven fresh-install wizard that discovers local/LAN capabilities, imports existing profiles when present, creates validated new profiles, and previews the generated topology without requiring manual JSON authoring.
- [ ] Add shared adapter-schema profile forms for llama.cpp, model-proxy, TTS model/bridge, tunnels, launchd, and generic agents, with transactional writes and advanced canonical JSON fallback.
- [ ] Add explicit manual/standalone/launchd lifecycle ownership and crash-only restart policies that never override an intentional operator stop.
- [ ] Add full-screen stack membership/dependency management and clarify catalog host aliases versus network hostnames throughout configuration and help.
- [ ] Add adapter-specific and arbitrary-profile schema forms after the schema contract stabilizes. Unknown fields remain canonical JSON in beta.
- [ ] Add deterministic corrective suggestions from active probes to the TUI. The beta TUI shows configuration validation only.
- [ ] Add a correlated model-proxy diagnostic exchange browser. The beta exposes component logs without modifying proxy traffic.
- [ ] Package an agent-neutral operational skill using `doctor`, `plan`, `status`, and JSON output with explicit approval for mutations and SSH provisioning.
- [ ] Add adapter-owned recovery policies with desired-running state, bounded retry/backoff, network-availability gating, restart count, last-exit status, and last-successful-recovery evidence. Keep automatic restart disabled by default except for explicitly supervised transports such as SSH tunnels.
- [ ] Add a network-outage acceptance fixture covering tunnel loss, launchd restart, endpoint recovery, status convergence, and client reconnection. Treat Desktop session reconnection as a client capability rather than proof that the tunnel failed.
- [ ] Add the loopback static WebUI over the same control library after the TUI stabilizes.
- [ ] Add stateless component relocation with adapter preflight, cutover, dependent endpoint update, and rollback. Do not treat a desired-state host edit as provisioning.
- [ ] Add component-native update check/plan/apply commands after provider backup, rollback, and post-update health contracts pass acceptance.

## Integration Roadmap

- [ ] Add an early-alpha MLXForge engine adapter after inference and lifecycle contracts stabilize.
- [ ] Add systemd and complete Debian/Rocky acceptance before declaring Linux support.
- [ ] Add optional recipes for Hermes, OpenClaw, Mnemosyne, RTK, and Headroom without making them core dependencies.
- [ ] Add a TTS Bridge provider contract for operator-supplied local or remote OpenAI-compatible speech endpoints; never ship voices or credentials.
- [ ] Integrate Secrets-Kit through explicit provider references after its release contract stabilizes, then retire plaintext `.env` injection.
- [ ] Publish an adapter SDK with a template, manifest schema, compatibility policy, conformance suite, test doubles, and uninstall contract.
- [ ] Add authenticated adapter catalog metadata before third-party installation is supported.
