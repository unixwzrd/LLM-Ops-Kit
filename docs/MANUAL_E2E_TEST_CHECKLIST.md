# Manual End-to-End Acceptance

Back: [Documentation index](./INDEX.md)

Record artifact version, SHA-256, host, architecture, timestamp, result, and evidence path for every section. Do not carry proof-of-concept or earlier release-candidate checks forward without rerunning them against the final artifact.

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
- [ ] Run `doctor --probe`, `status --all --json`, component/stack plans, and TUI startup.

## Minimal Install

- [ ] Install with `--minimal` into a separate root.
- [ ] Confirm CLI commands work and Textual is not installed.
- [ ] Confirm `llmops tui` returns a concise dependency instruction without a traceback.

## Lifecycle And Removal

- [ ] Run repair twice without changing configuration.
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
- [ ] Roll back to operator v1, validate status, and return to the beta candidate.

## Release Evidence

- [x] Regenerate two standardized dated operational reports from archived raw evidence and retain the raw logs as authority.
- [ ] Retain backups and prior runtimes through the beta observation period.
- [ ] Obtain explicit user approval, push the candidate branch, and require green macOS CI.
- [ ] Publish the prerelease assets only after every required release-audit item is checked.
