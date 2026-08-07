# Operator Checklist

**Created**: 2026-07-20
**Updated**: 2026-08-07

Back: [Documentation index](./INDEX.md)

## Install

- [ ] Verify `install-llmops.sha256` before execution.
- [ ] Run the installer and confirm `~/.local/bin/llmops --help`.
- [ ] Confirm `~/.local/llm-ops/current` and the managed Python environment exist.
- [ ] Run `llmops init` or review migrated canonical configuration.
- [ ] Confirm `control.authority_host` names a trusted inventory host.
- [ ] Use `llmops template list` and the Service Catalog to create any missing profiles and disabled components; do not hand-edit JSON for ordinary setup.
- [ ] Run `llmops doctor --probe` and `llmops adapter doctor`.

## Operate

- [ ] Run `llmops status` and review every `attention` or `error` condition; inspect lifecycle, health, and observability before acting.
- [ ] Use `llmops config effective component <component>` to verify resolved endpoints, templates, timeouts, environment references, and readiness probes.
- [ ] Use `llmops component version <component>` to compare desired and observed immutable runtimes; treat `stale-runtime` as attention.
- [ ] Treat `authority-only` as unobserved, not stopped; inspect it from the owning account.
- [ ] Use `component plan` before first-time lifecycle changes.
- [ ] Confirm the equivalent command shown by `llmops tui` before mutation.
- [ ] Run `llmops component logs <component> --list`, review the appropriate bounded channel or follow it, and verify the reported host, execution user, remote path, and readiness.
- [ ] Use `llmops operation list` and `llmops operation show <operation-id>` for lifecycle work dispatched from the TUI.
- [ ] Add one disabled component through the TUI Service Catalog and confirm placement, essential settings, required connections, inferred dependencies, equivalent CLI, and authority hash before applying.
- [ ] Import one reviewed local template through the Service Catalog and confirm the planned destination and equivalent `llmops template import` command before applying.
- [ ] Edit an existing component and verify Reset Section, Revert All, Cancel, Save, and Save & Restart preserve hidden advanced values and report shared-profile impact.
- [ ] For tool components, run their read-only Verify, telemetry, version, or metrics actions before approving any integration mutation.

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
