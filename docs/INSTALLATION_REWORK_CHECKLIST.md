# LLM-Ops-Kit Installation Rework Checklist

**Created**: 2026-04-27
**Updated**: 2026-07-16

## Phase 1: Inventory And Bootstrap

- [x] Define inventory schema.
- [x] Add example inventory for `llm`, `agent`, and `hybrid` hosts.
- [x] Add inventory validation command.
- [x] Implement SSH key discovery and generation planning.
- [x] Implement first-time remote key installation planning.
- [x] Verify noninteractive SSH planning for each host.
- [x] Create remote install directories planning.
- [x] Write host readiness marker planning.
- [x] Add checked-in `deploy/inventory.json` example.
- [ ] Document bootstrap recovery steps.

## Phase 2: Local Staging

- [x] Define staging directory layout under `~/.local/share/llm-ops/stage/<bundle_id>/`.
- [x] Build package artifact from the local repo/runtime.
- [x] Generate package manifest with checksums.
- [x] Render per-host config payloads from layered config.
- [x] Validate all host configs before push.
- [x] Add dry-run output showing planned host changes.
- [x] Keep staging output readable and inspectable.

## Phase 3: Parallel Push

- [x] Add host selection by name, role, and tag.
- [x] Transfer packages with parallel workers.
- [x] Transfer per-host config payloads.
- [x] Record per-host success/failure status.
- [x] Keep failed hosts isolated from successful hosts.
- [x] Add bounded retry support for failed transport commands.
- [x] Add summary output with elapsed time and failed steps.

## Phase 4: Remote Apply

- [x] Unpack package on target host.
- [x] Install or update runtime links.
- [x] Apply host-specific authoritative configuration in the same immutable release as code.
- [x] Restart selected services only.
- [x] Verify model server health on LLM hosts.
- [x] Verify agent runtime health on agent hosts.
- [x] Emit remote apply logs per host.
- [x] Preserve previous install for atomic code-and-configuration rollback.

## Phase 5: `modelctl` Refactor

- [x] Define config layer precedence.
- [x] Add effective config rendering.
- [x] Add source reporting for each setting.
- [x] Add config doctor support through `llmops-admin config-doctor`.
- [ ] Integrate layered config loader directly into `modelctl`.
- [ ] Simplify model start/restart config loading.
- [ ] Remove duplicate or implicit config paths inside `modelctl`.
- [ ] Update full user docs and examples after `modelctl` integration.

## Phase 6: Tests And Validation

- [x] Unit test inventory parsing.
- [x] Unit test config precedence.
- [x] Unit test SSH bootstrap planning.
- [x] Unit test parallel push result aggregation.
- [x] Integration test local staging layout.
- [x] Integration test dry-run deploy to multiple fake hosts.
- [x] Regression test existing single-host install flow.
- [x] Document manual acceptance test steps.
- [x] Test remote first install, upgrade, failed-upgrade rollback, and legacy
  directory migration on macOS.
