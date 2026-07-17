# Maintainer TODO

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

## Operator V1 Release Gate

- [x] Pass clean-checkout precheck on macOS.
- [x] Pass isolated fresh install, upgrade, repair, rollback, default uninstall, and purge uninstall on the model host.
- [x] Pass the same isolated lifecycle on the agent host.
- [x] Restore proof-of-concept fixtures and pass one-way migration twice on each host.
- [x] Deploy one clean immutable release to both hosts and confirm zero drift.
- [x] Restart one model component without restarting its dependents.
- [x] Pass one dependency-ordered cold stop and start of the configured agent stack.
- [ ] Retain the prior runtime through two operational reporting cycles.

## Post-V1

- [ ] Add guided executable and port discovery.
- [ ] Add Apple Silicon resource reporting.
- [ ] Add an optional loopback-only control API and static web UI after CLI stability.
- [ ] Integrate Secrets-Kit only through explicit provider references after its release contract stabilizes.
- [ ] Remove plaintext `.env` files from local secret injection after the external provider path is validated.
- [ ] Add signed release manifests if distribution expands beyond a trusted LAN.
