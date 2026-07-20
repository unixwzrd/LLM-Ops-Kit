# Maintainer TODO

**Created**: 2026-07-16
**Updated**: 2026-07-20

Back: [Documentation index](./INDEX.md)

## Completed Beta Implementation

- [x] Package the control library in a conventional `src/llmops_kit` layout with a locked UV project, console entry point, package resources, and one authoritative version.
- [x] Build a checksummed release archive with an offline Apple Silicon and Intel macOS wheelhouse.
- [x] Bootstrap checksum-verified UV and managed Python without Git, system Python, Conda, a source checkout, or shell-profile activation.
- [x] Support normal Textual and `--minimal` CLI installations, repair, immutable current/previous releases, local update, rollback, normal uninstall, and purge.
- [x] Preserve configuration and operational state outside immutable releases and record the actual custom install layout for initialization and probes.
- [x] Register built-in lifecycle adapters through a versioned entry-point registry and provide `adapter list`, `adapter show`, `adapter doctor`, and conformance fixtures.
- [x] Add global and per-component status with host, toolkit version, catalog/configuration hashes, authority, drift, reachability, and last synchronization.
- [x] Add coordinated remote update selection, preflight, staging, old-peer use, missing-peer bootstrap, sequential apply, post-apply identity verification, and rollback reporting.
- [x] Add one-way role-filtered configuration reconciliation with conflict refusal, immutable revisions, previous/current links, and no automatic merge.
- [x] Add the on-demand Textual dashboard over the shared planner/executor with component and stack views, logs, plans, lifecycle actions, existing-component editing, update actions, confirmation, and equivalent CLI commands.
- [x] Remove proof-of-concept repository synchronization, source-checkout deployment, runtime legacy reads, embedded Python shell blocks, and privileged Hermes/OpenClaw behavior.
- [x] Preserve test-only legacy migration fixtures; they are not installed in release artifacts.
- [x] Complete the prior operator-v1 48-hour live soak while retaining prior runtimes and checksummed backups.

## Beta Release Gates

- [x] Pass the dependency-complete Python suite and local precheck in the packaged UV environment. Current evidence: 115 tests pass on 2026-07-20.
- [x] Pass normal clean installation from a verified archive on isolated Apple Silicon and Intel macOS users.
- [ ] Repeat normal installation from the final committed release artifact on both macOS users after documentation and acceptance fixes stop changing the package.
- [x] Pass `--minimal` installation on isolated Apple Silicon and Intel macOS users and confirm the CLI works while `llmops tui` reports the omitted optional dependency cleanly.
- [x] Pass guided interactive model-profile reuse and deterministic non-interactive import against each test user's existing model profiles.
- [ ] Pass final-artifact repair, upgrade, rollback, normal uninstall, and purge on both macOS users.
- [ ] Pass Textual interaction tests for status, component/stack views, logs, lifecycle confirmation/cancellation, configuration validation, update check, and update cancellation.
- [ ] Pass coordinated two-host update tests for unreachable preflight, interrupted transfer, old-peer bootstrap, apply failure, automatic rollback, and mixed-version refusal.
- [ ] Pass live configuration reconciliation plan/apply/idempotence and independently edited target conflict refusal.
- [ ] Confirm identical topology/catalog hashes and global status from both trusted live hosts.
- [ ] Upgrade both live hosts from the preserved operator-v1 runtime to the final beta candidate, validate services, roll back once, and return to the candidate.
- [ ] Re-run model, embedding, TTS, model-proxy, tts-bridge, gateway, dashboard, tunnel, dependency, cascade, individual restart, and cold-start acceptance.
- [ ] Produce a clean local release commit and build exclusively from `git archive HEAD`; require clean status, documentation links, secret scan, private-path scan, archive audit, and ignored-file audit.
- [x] Regenerate the two missing standardized operational reports from 48 hourly archived source records. The reports preserve transient migration and cold-cycle exceptions rather than describing the cycles as uninterrupted steady state.
- [x] Run non-blocking installer experiments on Debian and Rocky. Both stop before mutation with the documented macOS-only beta error; Linux support is not claimed.
- [ ] Obtain explicit user approval before push or tag, then require green macOS CI and publish a GitHub prerelease with checksums, manifest, changelog, upgrade, and rollback instructions.

## Deferred From Beta

- [ ] Add adapter-specific and arbitrary-profile schema forms after the schema contract stabilizes. Unknown fields remain canonical JSON in beta.
- [ ] Add deterministic corrective suggestions from active probes to the TUI. The beta TUI shows configuration validation only.
- [ ] Add a correlated model-proxy diagnostic exchange browser. The beta exposes component logs without modifying proxy traffic.
- [ ] Package an agent-neutral operational skill using `doctor`, `plan`, `status`, and JSON output with explicit approval for mutations and SSH provisioning.
- [ ] Add a per-component supervisor/restart policy with desired-running state, bounded retry, restart count, and last-exit status. Keep automatic restart disabled by default.
- [ ] Add the loopback static WebUI over the same control library after the TUI stabilizes.

## Integration Roadmap

- [ ] Add an early-alpha MLXForge engine adapter after inference and lifecycle contracts stabilize.
- [ ] Add systemd and complete Debian/Rocky acceptance before declaring Linux support.
- [ ] Add optional recipes for Hermes, OpenClaw, Mnemosyne, RTK, and Headroom without making them core dependencies.
- [ ] Add a TTS Bridge provider contract for operator-supplied local or remote OpenAI-compatible speech endpoints; never ship voices or credentials.
- [ ] Integrate Secrets-Kit through explicit provider references after its release contract stabilizes, then retire plaintext `.env` injection.
- [ ] Publish an adapter SDK with a template, manifest schema, compatibility policy, conformance suite, test doubles, and uninstall contract.
- [ ] Add authenticated adapter catalog metadata before third-party installation is supported.
