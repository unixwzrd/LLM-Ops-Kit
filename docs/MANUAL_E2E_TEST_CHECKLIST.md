# Manual End-to-End Acceptance

Back: [Documentation index](./INDEX.md)

## Source and Backups

- [x] Create checksummed runtime and configuration backups on both hosts.
- [x] Commit the release candidate locally and confirm a clean source tree.
- [x] Confirm `scripts/precheck --release` passes.
- [x] Build and distribute test source exclusively from `git archive HEAD`.

## Fresh Installation

- [x] Install into isolated install, config, data, state, cache, and public command roots on both hosts.
- [x] Exercise interactive model discovery and selective import against saved profiles.
- [x] Exercise deterministic non-interactive import and compare output.
- [x] Confirm legacy `env` normalization and secret-reference conversion.
- [x] Bind selected chat, embedding, and TTS defaults while leaving every generated component disabled.
- [x] Run static doctor, active probe, configuration display, and non-mutating plans.
- [x] Run repair twice, upgrade the isolated runtime, and exchange current and previous through rollback.
- [x] Verify default uninstall preserves configuration and purge removes only selected toolkit roots.

## Migration

- [x] Preview real proof-of-concept fixtures and inspect every mapping, warning, and skip.
- [x] Confirm unknown inputs block normal migration and `--allow-partial` migrates only classified inputs.
- [x] Confirm repeat migration is an unchanged no-op and changed sources require reviewed force.
- [x] Confirm runtime behavior never changes when legacy files are edited after migration.

## Live Upgrade and Runtime

- [x] Upgrade both live hosts without changing canonical configuration hashes.
- [x] Confirm current and previous release targets and zero drift.
- [x] Restart one model component without restarting dependents.
- [x] Confirm stop refuses active dependents without force or cascade.
- [x] Confirm cascade order is dependency-safe and failed starts preserve pre-existing components.
- [x] Run one dependency-ordered cold stop/start.
- [x] Pass model, embedding, proxy, TTS, bridge, agent, dashboard, tunnel, and reconnection protocol checks.
- [x] Confirm `llmops status`, component/profile drill-down, tag filtering, and `--json` output from the administrator configuration.
- [x] Roll back to the prior runtime, validate, and return to the release candidate.

## Observation

- [x] Restart the soak clock after restoring the crashed Qwen3TTS component and passing an end-to-end voice-clone request through `tts-bridge`.
- [ ] Run the complete managed environment for a 48-hour soak period.
- [ ] Capture `llmops status --json` at the start and after each of two consecutive scheduled daily operational reports.
- [ ] Confirm both reports complete without unexplained component restarts, failed health checks, drift, protocol failures, or missing metrics.
- [ ] Retain backups and prior runtimes through the completed soak period.
- [ ] Record final evidence and mark the release audit only from current results.
