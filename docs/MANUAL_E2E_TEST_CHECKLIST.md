# Manual End-to-End Acceptance

Back: [Documentation index](./INDEX.md)

## Source and Backups

- [ ] Create checksummed runtime and configuration backups on both hosts.
- [ ] Commit the release candidate locally and confirm a clean source tree.
- [ ] Confirm `scripts/precheck --release` passes.
- [ ] Build and distribute test source exclusively from `git archive HEAD`.

## Fresh Installation

- [ ] Install into isolated install, config, data, state, cache, and public command roots on both hosts.
- [ ] Exercise interactive model discovery and selective import against saved profiles.
- [ ] Exercise deterministic non-interactive import and compare output.
- [ ] Confirm legacy `env` normalization and secret-reference conversion.
- [ ] Bind selected chat, embedding, and TTS defaults while leaving every generated component disabled.
- [ ] Run static doctor, active probe, configuration display, and non-mutating plans.
- [ ] Run repair twice, upgrade the isolated runtime, and exchange current and previous through rollback.
- [ ] Verify default uninstall preserves configuration and purge removes only selected toolkit roots.

## Migration

- [ ] Preview real proof-of-concept fixtures and inspect every mapping, warning, and skip.
- [ ] Confirm unknown inputs block normal migration and `--allow-partial` migrates only classified inputs.
- [ ] Confirm repeat migration is an unchanged no-op and changed sources require reviewed force.
- [ ] Confirm runtime behavior never changes when legacy files are edited after migration.

## Live Upgrade and Runtime

- [ ] Upgrade both live hosts without changing canonical configuration hashes.
- [ ] Confirm current and previous release targets and zero drift.
- [ ] Restart one model component without restarting dependents.
- [ ] Confirm stop refuses active dependents without force or cascade.
- [ ] Confirm cascade order is dependency-safe and failed starts preserve pre-existing components.
- [ ] Run one dependency-ordered cold stop/start.
- [ ] Pass model, embedding, proxy, TTS, bridge, agent, dashboard, tunnel, and reconnection protocol checks.
- [ ] Roll back to the prior runtime, validate, and return to the release candidate.

## Observation

- [ ] Retain backups and prior runtimes through two successful operational reporting cycles.
- [ ] Record final evidence and mark the release audit only from current results.
