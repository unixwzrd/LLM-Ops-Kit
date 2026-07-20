# Remote Operation And Desired State

**Created**: 2026-07-16
**Updated**: 2026-07-20

Back: [Documentation index](./INDEX.md)

The proof-of-concept source-checkout deployment command has been retired. Runtime distribution and desired-state synchronization are separate, repository-free operations.

## Runtime Distribution

```bash
llmops update --host <inventory-name> --plan --version <version>
llmops update --host <inventory-name> --apply --version <version>
llmops update --all-hosts --apply --version <version>
```

`--host` is repeatable. `--all-hosts` selects peer-observable managed hosts and excludes authority-only desktop accounts unless explicitly selected.

## Configuration Reconciliation

```bash
llmops config reconcile --host <inventory-name> --plan --json
llmops config reconcile --all-hosts --apply --yes
```

The authority generates a complete secret-free catalog and a role-filtered configuration revision for each host. Each target verifies its current manifest before replacement. A changed file that no longer matches its manifest is reported as a conflict and is not overwritten or merged.

Applied revisions live under `~/.local/llm-ops/config-revisions/`; `current-config` selects the active revision atomically. Runtime releases and configuration revisions therefore remain independently recoverable while retaining explicit hashes in status output.
