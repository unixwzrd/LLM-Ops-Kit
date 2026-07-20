# Operator Checklist

**Created**: 2026-07-20
**Updated**: 2026-07-20

Back: [Documentation index](./INDEX.md)

## Install

- [ ] Verify `install-llmops.sha256` before execution.
- [ ] Run the installer and confirm `~/.local/bin/llmops --help`.
- [ ] Confirm `~/.local/llm-ops/current` and the managed Python environment exist.
- [ ] Run `llmops init` or review migrated canonical configuration.
- [ ] Run `llmops doctor --probe` and `llmops adapter doctor`.

## Operate

- [ ] Run `llmops status` and review every `unreachable`, `error`, and `not-running` result.
- [ ] Treat `authority-only` as unobserved, not stopped; inspect it from the owning account.
- [ ] Use `component plan` before first-time lifecycle changes.
- [ ] Confirm the equivalent command shown by `llmops tui` before mutation.
- [ ] Review component logs after restart and verify readiness.

## Synchronize

- [ ] Run `llmops config reconcile --all-hosts --plan --json`.
- [ ] Resolve any manual-drift conflict before applying.
- [ ] Apply with `--yes` only after reviewing full trusted-controller and role-filtered component-host targets.
- [ ] Confirm matching catalog/configuration hashes through `llmops status --json`.

## Upgrade

- [ ] Preserve current backups and confirm `previous` is valid.
- [ ] Run `llmops update --all-hosts --plan --version <version>`.
- [ ] Apply and confirm all selected hosts report the same version.
- [ ] Restart only components whose runtime integration changed.
- [ ] Run protocol and log checks.

## Recovery

- [ ] Use `llmops rollback` to exchange immutable releases.
- [ ] Use the installed `install-runtime.sh --repair` when links or install state are damaged.
- [ ] Restore a configuration revision by selecting its directory through `current-config` only after verifying its manifest.
- [ ] Do not merge independently edited target configuration automatically.

## Removal

- [ ] Use normal uninstall to preserve configuration and state.
- [ ] Use purge only after confirming LLM-Ops-Kit-owned configuration, data, state, and cache may be removed.
- [ ] Confirm model weights and agent-owned data remain untouched.
