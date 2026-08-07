# Release Audit

**Created**: 2026-07-18
**Updated**: 2026-08-07

Back: [Documentation index](./INDEX.md)

## Implemented

- [x] `llmops` is the sole public command and its help matches public documentation.
- [x] Canonical runtime configuration is JSON; legacy inputs are reachable only through explicit one-time migration/import.
- [x] Hermes and OpenClaw are ordinary profiles, not privileged core targets.
- [x] The standard Python package, dual-architecture wheelhouse, and normal/minimal installation paths are present.
- [x] Installed commands use the application-owned Python and do not require shell-profile activation.
- [x] Release archives exclude tests, migration fixtures, private topology, `.env` files, model weights, logs, state databases, and maintainer-only tooling.
- [x] A verified archive installs normally on isolated Apple Silicon and Intel macOS users.
- [x] Dependency-complete regression and precheck suites pass in the packaged UV environment.
- [x] Experimental Debian and Rocky installer runs reject the unsupported platform before creating an install root.

## Required Before Approval

- [x] Confirm `0.9.0b16` status records contain lifecycle, health, condition, observability, execution user, component version, desired/observed runtime, and toolkit version without the removed legacy status alias on both trusted hosts. The chat model was intentionally left stopped for separate MLXForge testing after the UI-only update.
- [x] Confirm prompt replay through the media-history template removes textual image tool results and assistant decode/copy calls while proxy forwarding remains byte-preserving.
- [x] Confirm a dedicated structured vision request retains its `image_url` in the raw request and renders exactly one Qwen vision placeholder. Captured requests met both conditions; their upstream `500 Compute error` responses remain a model-engine issue.
- [x] Build the schema-v2 candidate from clean committed source and confirm its wheel contains all 12 built-in service templates plus JSON Schema and Textual dependencies.
- [x] Migrate checksummed copies and the live authority configuration to schema version 2 with no profile, component, stack, execution user, endpoint, lifecycle, or log-channel loss; both resulting nine-component copies passed `doctor` before live cutover.
- [x] Verify schema mutation and `llmops tui` route from the non-authority trusted host to the designated authority and stale hashes are refused.
- [ ] Complete the RTK Hermes canary backup/enable/disable/rollback acceptance only after explicit operator approval. The current dry run is non-mutating and is not canary acceptance.
- [x] Confirm CLI and TUI both refuse a target-only stop with active dependents unless cascade or force is explicitly selected.
- [x] Pass keyboard navigation, high-contrast rendering, help, settings, branding, automatic-refresh pause, and bounded topology acceptance using the installed Textual wheel. Six artifact-boundary TUI tests passed on 2026-07-21 with repository source removed from `PYTHONPATH`.
- [x] Build the candidate directly from a committed `git archive HEAD` without adding a synthetic `.git` directory, then install and inspect the resulting checksummed artifact in isolated roots.
- [ ] Pass final normal/minimal install, repair, upgrade, rollback, uninstall, purge, migration, TUI, remote update, reconciliation, and protocol acceptance.
- [x] Pass the `0.9.0b41` source precheck with the locked UV runtime, including 203 guided-configuration, template-declared-log, full-screen-log-viewing, interrupt-cleanup, and launchd-symmetry regressions.
- [ ] Build `0.9.0b41` from the clean local candidate commit and repeat normal/minimal install, repair, upgrade, rollback, uninstall, purge, and cold-stack acceptance under both isolated macOS test users during the scheduled acceptance window.
- [x] Confirm all Markdown links, command examples, and public paths resolve.
- [x] Confirm no release file or archive member contains private paths, addresses, credentials, topology, model weights, voice samples, caches, or development history.
- [x] Confirm both trusted live hosts report the same catalog/topology identity and expected host-specific complete configuration identity.
- [x] Produce the missing two dated operational reports from archived evidence, retaining the archived logs as authority and recording transient failures explicitly.
- [ ] Obtain explicit user approval before push or tag.
- [ ] Require green macOS CI after the candidate branch is pushed.
