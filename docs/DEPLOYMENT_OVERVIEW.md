# Deployment Overview

Back: [Documentation Index](./INDEX.md)

## Authority

The administrator checkout and its canonical JSON configuration are the one-way desired-state authority. Managed hosts do not need source checkouts and their local configuration changes are never merged automatically.

## Authoritative Deployment

```bash
scripts/llmops-admin deploy --config-home ~/.config/llm-ops --bundle-id <bundle-id> --dry-run
scripts/llmops-admin deploy --config-home ~/.config/llm-ops --bundle-id <bundle-id>
```

`deploy` performs these steps:

1. Validate inventory, stacks, components, dependencies, profiles, feature gates, and port bindings.
2. Refuse a dirty source checkout unless `--allow-dirty` is explicit.
3. Build the runtime package.
4. Build a checksummed, secret-free, role-filtered configuration snapshot for each selected host.
5. Record the Git commit, dirty state, toolkit version, schema version, package hash, and configuration hashes in the manifest.
6. Push package, manifest, compatibility config, and authoritative snapshot with bounded retry.
7. Verify every remote hash before extraction.
8. Extract code and configuration into one immutable release.
9. Atomically update `current` and preserve the old target as `previous`.
10. Refresh managed runtime links and verify the role-specific command surface.
11. Compare the active release with the desired bundle and report drift.

## Separate Phases

The phases remain available for controlled rollout:

```bash
scripts/llmops-admin stage --config-home ~/.config/llm-ops --require-authoritative-config --bundle-id <bundle-id>
scripts/llmops-admin push --stage ~/.local/share/llm-ops/stage/<bundle-id>
scripts/llmops-admin apply --stage ~/.local/share/llm-ops/stage/<bundle-id>
scripts/llmops-admin drift --stage ~/.local/share/llm-ops/stage/<bundle-id>
```

Use separate phases for side-by-side canaries and host-by-host migration.

## Host Filtering

Use `--host-name`, `--role`, or `--tag` to select deployment targets. Each host receives only the profiles for its enabled components. Model weights, runtime logs, state databases, `.env` files, and secret values are never included.

## Dirty Canaries

`--allow-dirty` exists for intentional testing before a commit. The deployment manifest records the dirty state and should not be treated as a publishable release. Normal deployments should use a clean commit.

## Failure Behavior

Push and apply retry failed transport commands up to three times with bounded exponential delay. Apply verifies all content before switching `current`. If post-switch setup fails, it restores both `current` and `previous` and removes the failed release.

Pre-existing services are not restarted unless explicitly requested. Deployment changes installed code and configuration; component lifecycle remains a separate operation.

## Drift

```bash
llmops drift --stage ~/.local/share/llm-ops/stage/<bundle-id> --json
```

Drift compares the desired bundle ID, manifest hash, and active compatibility configuration hashes with each selected host. It is read-only.

## Rollback

```bash
llmops rollback --dry-run
llmops rollback
```

Rollback atomically exchanges `current` and `previous` on each selected host and refreshes runtime links. Because configuration is inside the release, code and configuration roll back together.

See [Upgrade and Rollback](./UPGRADE_AND_ROLLBACK.md) for acceptance checks.
