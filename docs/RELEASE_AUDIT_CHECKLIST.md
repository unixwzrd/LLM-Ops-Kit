# Release Audit

Back: [Documentation index](./INDEX.md)

- [ ] Public commands match `README.md` and `llmops --help`.
- [ ] Canonical configuration is JSON-only at runtime.
- [ ] Legacy configuration is reachable only through explicit initialization import or `llmops migrate-config`.
- [ ] No agent is privileged by core code or examples.
- [ ] Deployment bundles contain no secrets, `.env` files, model weights, logs, state databases, tests, or private topology.
- [ ] Dirty deployment and obsolete generated source paths are refused.
- [ ] Fresh install, upgrade, repair, rollback, uninstall, and purge pass under isolated roots on both macOS hosts.
- [ ] Clean-archive proxy execution works without an ignored wrapper.
- [ ] All Markdown links resolve and public files contain no private machine defaults.
- [ ] `scripts/precheck --release` passes from a committed clean source tree.
- [ ] Release notes describe configuration changes, migration, upgrade, rollback, and uninstall.
- [ ] Two operational reporting cycles pass before release tagging.
