# Manual End-to-End Acceptance

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

## Source

- [ ] `git status --short` is clean.
- [ ] `scripts/precheck` passes.
- [ ] `llmops --help` exposes only the documented public commands.
- [ ] A repository search finds no removed synchronization commands or agent-specific adapters.

## Isolated Installation

- [ ] Install from a clean checkout into isolated install, config, data, state, cache, and public-bin roots.
- [ ] Confirm `current` resolves to the new release and no `previous` exists on first install.
- [ ] Run `llmops init`, `doctor`, `config show`, and non-mutating plans.
- [ ] Run `--repair` twice and confirm idempotence.
- [ ] Upgrade from a second release and confirm `previous` identifies the first release.
- [ ] Uninstall and confirm unrelated model and agent data remains untouched.
- [ ] Repeat with `--purge` and confirm only selected LLM-Ops-Kit roots are removed.

## Migration

- [ ] Restore proof-of-concept fixtures into an isolated legacy root.
- [ ] Run migration dry-run and inspect destinations.
- [ ] Run migration and confirm only JSON plus the migration marker is written.
- [ ] Run migration again and confirm an unchanged no-op.
- [ ] Change a source fixture and confirm migration refuses without `--force`.
- [ ] Confirm runtime behavior is unchanged when legacy files are edited after migration.

## Deployment

- [ ] Dry-run a selected-host deployment.
- [ ] Inspect package and host snapshots for secrets, `.env` files, tests, logs, databases, and model weights.
- [ ] Deploy to both hosts and confirm code and host-filtered configuration share one release.
- [ ] Confirm `llmops drift --json` reports no differences.
- [ ] Exchange `current` and `previous` with rollback, verify, then return to the new release.

## Runtime

- [ ] Start missing dependencies through one component start.
- [ ] Restart a model component and confirm dependents remain running.
- [ ] Confirm stop refuses active dependents without `--force` or `--cascade`.
- [ ] Confirm cascade order is dependency-safe.
- [ ] Confirm a failed start leaves pre-existing components running.
- [ ] Run chat, embedding, proxy, TTS, agent, dashboard, and tunnel protocol checks for the configured environment.
