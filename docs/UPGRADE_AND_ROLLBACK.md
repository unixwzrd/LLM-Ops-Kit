# Upgrade And Rollback

**Created**: 2026-07-16
**Updated**: 2026-08-21

Back: [Documentation index](./INDEX.md)

## Check And Plan

```bash
llmops update --check
llmops update --plan --version <version> --json
llmops update --local-only --plan --version <version> --json
```

Check and plan do not download or mutate a release. A local artifact can be selected with `--archive` and `--checksum-file`.

## Apply

```bash
llmops update --apply --version <version>
llmops update --local-only --apply --version <version>
```

Update check, plan, apply, and rollback select every host in the reconciled catalog by default. Apply preflights macOS, SSH, disk space, and installed state; stages one verified artifact everywhere; then applies sequentially. If any catalog host is unreachable, preflight stops before mutation. If a later host fails, hosts changed by the invocation are rolled back and the mixed-version condition is reported. `--local-only` is reserved for deliberate single-installation work and for the internal per-host phase of a coordinated operation.

An older peer can use its existing `llmops update` implementation to invoke the new archive installer. A peer without `llmops` is bootstrapped from the staged, remotely verified archive.

## Manifest-Approved Automatic Update

When the reconciled `products.json` entry for `llm-ops-kit` sets `auto_update: true` and supplies `release_repository`, every installed invocation compares its selected immutable runtime with that entry's `latest_version`. A mismatch uses the checksum-verified updater and re-executes the original command from the newly selected release. Both the target version and artifact repository are manifest policy rather than application constants. `update` and `rollback` commands bypass this pre-dispatch hook to prevent recursion. An unavailable update emits a warning and continues with the current runtime; managed components are never restarted by toolkit self-update.

## Rollback And Repair

```bash
llmops rollback
bash ~/.local/llm-ops/current/scripts/install-runtime.sh --repair
```

Rollback exchanges `current` and `previous`, reconstructs managed links, and updates install state. A second rollback exchanges them again. Repair verifies the active application environment and rebuilds managed links without creating a release.

## Uninstall

```bash
bash ~/.local/llm-ops/current/scripts/uninstall-runtime.sh
bash ~/.local/llm-ops/current/scripts/uninstall-runtime.sh --purge
```

Normal uninstall preserves canonical configuration, data, state, and cache. Purge removes LLM-Ops-Kit-owned roots. Model weights, agent state, logs owned by other products, and source defaults are never removed.
