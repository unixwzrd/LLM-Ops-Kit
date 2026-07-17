# Maintainer TODO

Back: [Documentation index](./INDEX.md)

## Operator V1 Release Gate

- [x] Pass release precheck from a clean committed source tree.
- [x] Pass installation from `git archive HEAD` on both supported hosts.
- [x] Pass guided and non-interactive model-profile import using real saved profiles.
- [x] Pass classified migration using real model, service, agent, inventory, and unknown-input fixtures.
- [x] Pass isolated fresh install, upgrade, repair, rollback, default uninstall, and purge uninstall on both hosts.
- [x] Upgrade the live two-host runtime without changing canonical configuration hashes.
- [x] Confirm zero deployment drift and protocol health for model, embedding, proxy, TTS, bridge, agent, dashboard, and tunnel components.
- [x] Pass component restart, dependency enforcement, cascade behavior, and complete cold stop/start.
- [ ] Complete a 48-hour soak spanning two consecutive scheduled daily operational reports while retaining the prior runtime and backups.
- [ ] Obtain a green macOS CI run after the release candidate is pushed for review.

## General-User Distribution Gate

- [ ] Add one application-owned Python runtime environment with a checksum-verified uv or `venv` bootstrap, offline/error handling, dependency locking, repair, upgrade, rollback, and purge semantics. Python-backed launchd services should use its explicit interpreter path without sourcing interactive shell profiles.
- [ ] Add portable read-only observer snapshots so any trusted configured host can run global `llmops status` without receiving mutation authority or secret material.
- [ ] Package an agent-neutral LLM-Ops-Kit skill that uses `doctor`, `plan`, `status`, and JSON output for setup and operations while requiring explicit approval for mutations and SSH provisioning.

## Post-V1

- [ ] Integrate Secrets-Kit only through explicit provider references after its release contract stabilizes.
- [ ] Remove plaintext `.env` secret injection after the external provider path is validated.
- [ ] Add signed release manifests if distribution expands beyond a trusted LAN.
- [ ] Consider guided model downloads only as a separately approved feature.
