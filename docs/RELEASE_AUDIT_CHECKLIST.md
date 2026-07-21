# Release Audit

**Created**: 2026-07-18
**Updated**: 2026-07-21

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

- [ ] Confirm `0.9.0b8` status records contain lifecycle, health, condition, observability, execution user, component version, desired/observed runtime, and toolkit version without the removed legacy status alias on both trusted hosts.
- [ ] Confirm prompt replay through the installed media-history template retains exactly one historical image-bearing tool response and proxy forwarding remains byte-preserving.
- [ ] Confirm CLI and TUI both refuse a target-only stop with active dependents unless cascade or force is explicitly selected.
- [x] Pass keyboard navigation, high-contrast rendering, help, settings, branding, automatic-refresh pause, and bounded topology acceptance using the installed Textual wheel. Six artifact-boundary TUI tests passed on 2026-07-21 with repository source removed from `PYTHONPATH`.
- [x] Build the candidate directly from a committed `git archive HEAD` without adding a synthetic `.git` directory, then install and inspect the resulting checksummed artifact in isolated roots.
- [ ] Pass final normal/minimal install, repair, upgrade, rollback, uninstall, purge, migration, TUI, remote update, reconciliation, and protocol acceptance.
- [x] Confirm all Markdown links, command examples, and public paths resolve.
- [x] Confirm no release file or archive member contains private paths, addresses, credentials, topology, model weights, voice samples, caches, or development history.
- [x] Confirm both trusted live hosts report the same catalog/topology identity and expected host-specific complete configuration identity.
- [x] Produce the missing two dated operational reports from archived evidence, retaining the archived logs as authority and recording transient failures explicitly.
- [ ] Obtain explicit user approval before push or tag.
- [ ] Require green macOS CI after the candidate branch is pushed.
