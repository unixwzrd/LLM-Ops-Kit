# Manual End-to-End Acceptance

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

## Source

- [x] `git status --short` is clean.
- [x] `scripts/precheck` passes.
- [x] `llmops --help` exposes only the documented public commands.
- [x] A repository search finds no removed synchronization commands or agent-specific adapters.

## Isolated Installation

- [x] Install from a clean checkout into isolated install, config, data, state, cache, and public-bin roots.
- [x] Confirm `current` resolves to the new release and no `previous` exists on first install.
- [x] Run `llmops init`, `doctor`, `config show`, and non-mutating plans.
- [x] Run `--repair` twice and confirm idempotence.
- [x] Upgrade from a second release and confirm `previous` identifies the first release.
- [x] Uninstall and confirm unrelated model and agent data remains untouched.
- [x] Repeat with `--purge` and confirm only selected LLM-Ops-Kit roots are removed.

## Migration

- [x] Restore proof-of-concept fixtures into an isolated legacy root.
- [x] Run migration dry-run and inspect destinations.
- [x] Run migration and confirm only JSON plus the migration marker is written.
- [x] Run migration again and confirm an unchanged no-op.
- [x] Change a source fixture and confirm migration refuses without `--force`.
- [x] Confirm runtime behavior is unchanged when legacy files are edited after migration.

## Deployment

- [x] Dry-run a selected-host deployment.
- [x] Inspect package and host snapshots for secrets, `.env` files, tests, logs, databases, and model weights.
- [x] Deploy to both hosts and confirm code and host-filtered configuration share one release.
- [x] Confirm `llmops drift --json` reports no differences.
- [x] Exchange `current` and `previous` with rollback, verify, then return to the new release.

## Runtime

- [x] Start missing dependencies through one component start.
- [x] Restart a model component and confirm dependents remain running.
- [x] Confirm stop refuses active dependents without `--force` or `--cascade`.
- [x] Confirm cascade order is dependency-safe.
- [x] Confirm a failed start leaves pre-existing components running.
- [x] Run chat, embedding, proxy, TTS, agent, dashboard, and tunnel protocol checks for the configured environment.
