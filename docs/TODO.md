# Maintainer TODO

Back: [Documentation index](./INDEX.md)

## Operator V1 Release Gate

- [ ] Pass release precheck from a clean committed source tree.
- [ ] Pass installation from `git archive HEAD` on both supported hosts.
- [ ] Pass guided and non-interactive model-profile import using real saved profiles.
- [ ] Pass classified migration using real model, service, agent, inventory, and unknown-input fixtures.
- [ ] Pass isolated fresh install, upgrade, repair, rollback, default uninstall, and purge uninstall on both hosts.
- [ ] Upgrade the live two-host runtime without changing canonical configuration hashes.
- [ ] Confirm zero deployment drift and protocol health for model, embedding, proxy, TTS, bridge, agent, dashboard, and tunnel components.
- [ ] Pass component restart, dependency enforcement, cascade behavior, and complete cold stop/start.
- [ ] Retain the prior runtime and backups through two successful operational reporting cycles.
- [ ] Obtain a green macOS CI run after the release candidate is pushed for review.

## Post-V1

- [ ] Add an optional loopback-only control API and static web UI after CLI stability.
- [ ] Integrate Secrets-Kit only through explicit provider references after its release contract stabilizes.
- [ ] Remove plaintext `.env` secret injection after the external provider path is validated.
- [ ] Add signed release manifests if distribution expands beyond a trusted LAN.
- [ ] Consider guided model downloads only as a separately approved feature.
