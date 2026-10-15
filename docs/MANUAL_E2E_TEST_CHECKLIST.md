# Manual End-to-End Acceptance

**Created**: 2026-07-17
**Updated**: 2026-10-14

Back: [Documentation index](./INDEX.md)

Record artifact version, SHA-256, host, architecture, timestamp, result, and evidence path for every section. Do not carry proof-of-concept or earlier release-candidate checks forward without rerunning them against the final artifact.

## b54 Release Disposition

Published prerelease `0.9.0b54` is frozen to clean source `007b0578d95e96f5f8f080fd2f726a1424cf9d84` and archive SHA-256 `9149eb9df7786cc75db474256cdf235d830531669a0f12c5472f98f98584dec6`. The documentation changes recording publication are later commits; they do not replace that artifact.

| Acceptance area | Exact b54 evidence |
|---|---|
| Source and CI | 288 tests, release precheck, and exact-commit macOS CI passed |
| Installed artifact | 108 control tests passed on Apple Silicon and Intel with source excluded |
| Fresh installation | Normal and minimal installs, repair, preserving uninstall, reinstall, and purge passed in disposable homes on both architectures; Textual presence/absence and installed-wheel provenance verified |
| Live operations | All three contexts remain on b54; authority-lock contention refused before mutation, one authority-controlled startup completed, 11 components healthy, and nine protocol checks passed |
| Retention | Current and previous are protected; incomplete or altered legacy installations are retained, not reclassified to bypass guards |

These are targeted b54 acceptance results, not a claim that every historical scenario below was repeated. Earlier rollback/return-forward evidence remains historical; the current development policy is fix-forward, with no additional live version cycling or stack restart merely for release bookkeeping. Normal uninstall and purge acceptance affects disposable fixtures only. Published-asset verification is recorded in the release closure evidence and must not be inferred solely from a successful upload.

The remaining sections are the reusable manual scenario checklist. An unchecked historical box is not an assertion that the corresponding b54 check failed, and an older checked box is not substitute evidence for a new artifact.

## Preserve

- [x] Preserve checksummed live runtime and configuration backups on both managed hosts.
- [x] Retain the operator-v1 `current` and `previous` runtime evidence during beta work.
- [ ] Record final backup hashes and verify one archive listing before live upgrade.

## Source And Artifact

- [ ] Create the local release commit and confirm clean Git status.
- [ ] Run `uv sync --locked --extra tui` and `uv run --locked --extra tui ./scripts/precheck`.
- [ ] Build exclusively from `git archive HEAD` and verify the release archive checksum and per-file manifest.
- [ ] Confirm the archive contains both native macOS `MarkupSafe` wheels and no source checkout, tests, fixtures, secrets, private paths, or ignored residue.

## Fresh Normal Install

- [ ] Install the same final artifact under the isolated Apple Silicon and Intel macOS users with Git, Python, Conda, UV, and user-local tools removed from `PATH`.
- [ ] Confirm checksum-verified UV bootstrap, managed CPython, immutable release, `current`, public `llmops`, and Textual installation.
- [ ] Run `adapter doctor` before initialization.
- [ ] Exercise interactive saved-model discovery and selective import.
- [ ] Repeat initialization non-interactively with explicit flags and compare canonical output.
- [ ] Confirm imported secret literals become references and source defaults remain unchanged.
- [ ] Run `doctor --probe`, `status --all --json`, component/stack plans, topology table/JSON/Mermaid output, and TUI startup.
- [ ] Confirm a running component with failed readiness reports running lifecycle and degraded health, while an intentionally unobservable component reports authority-only observability.
- [ ] Confirm arrow selection updates TUI details, automatic refresh pauses during dialogs, help/settings open, and active-dependent stop requires cascade or force.
- [ ] List declared log channels, read a bounded remote log, interrupt CLI follow, and verify host, execution user, path, metadata, and child-process cleanup.
- [ ] Open the full-screen TUI log viewer, change channel and line limit, scroll, refresh, start and stop follow, close with Escape, and confirm dashboard refresh was paused.
- [ ] Create a disabled component through all four Service Catalog steps and confirm required endpoints, inferred dependencies, affected files, authority hash, equivalent CLI, and no implicit restart.
- [ ] Import a reviewed local generic-service template through the TUI, then add its component without editing JSON or changing core source.
- [ ] Edit a shared profile and confirm the warning names every affected component; verify hidden advanced values survive Reset Section, Revert All, Save, and Save & Restart.

## Minimal Install

- [ ] Install with `--minimal` into a separate root.
- [ ] Confirm CLI commands work and Textual is not installed.
- [ ] Confirm `llmops tui` returns a concise dependency instruction without a traceback.

## Lifecycle And Removal

- [ ] Run repair twice without changing configuration.
- [ ] Stop an initially loaded managed launchd component, then start it and restart it in both loaded and unloaded states; verify bootstrap precedes kickstart and no lifecycle lock remains held.
- [ ] Upgrade to a second test artifact and verify `current`, `previous`, version, and configuration identity.
- [ ] Roll back and return to the candidate.
- [ ] Normal uninstall and confirm configuration/state preservation.
- [ ] Reinstall, purge, and confirm only explicitly owned toolkit roots are removed.
- [ ] Confirm models, agent data, logs outside toolkit roots, and source defaults remain untouched.

## Textual Console

- [ ] Verify global component and stack views, selection details, refresh, logs, and update check.
- [ ] Verify lifecycle and configuration mutations show the exact CLI command and operation plan.
- [ ] Verify cancel makes no change and confirm produces the same result as the displayed CLI command.
- [ ] Verify invalid configuration is refused transactionally and the prior configuration remains active.

## Remote Update And Reconciliation

- [ ] Plan a two-host update from each trusted control host.
- [ ] Verify unreachable preflight and interrupted transfer change no host.
- [ ] Bootstrap an older or missing peer from the staged installer and configured absolute paths.
- [ ] Inject a later-host apply failure and confirm already-updated hosts roll back.
- [ ] Confirm successful apply reports version, catalog hash, and configuration hash for each host.
- [ ] Plan and apply configuration reconciliation with complete trusted-controller snapshots and role-filtered component-host snapshots, then rerun it as an idempotent no-op.
- [ ] Independently edit a target revision and confirm conflict refusal with no automatic merge.

## Live Acceptance

- [ ] Upgrade both live hosts without restarting unaffected components.
- [ ] Confirm matching global topology/catalog identity and expected host-specific complete configuration identity.
- [ ] Restart individual model, proxy, bridge, and agent components from either trusted host.
- [ ] Verify dependency refusal, cascade order, partial-start rollback, and one complete cold stop/start.
- [ ] Pass chat, embedding, TTS, proxy rendering, bridge, gateway, dashboard, tunnel, Desktop reconnection, and Telegram fallback checks.
- [ ] Interrupt LAN connectivity long enough to break the SSH tunnel; verify the supervisor retries with bounded cadence, the local listener and HTTP endpoint recover, and status distinguishes recovered transport from a client session that still requires reconnection.
- [ ] Roll back to operator v1, validate status, and return to the beta candidate.

## Release Evidence

- [x] Regenerate two standardized dated operational reports from archived raw evidence and retain the raw logs as authority.
- [ ] Retain backups and prior runtimes through the beta observation period.
- [ ] Obtain explicit user approval, push the candidate branch, and require green macOS CI.
- [ ] Publish the prerelease assets only after every required release-audit item is checked.
