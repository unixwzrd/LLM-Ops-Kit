# Release Audit

Back: [Documentation index](./INDEX.md)

- [x] Public commands match `README.md` and `llmops --help`.
- [x] Canonical configuration is JSON-only at runtime.
- [x] Legacy configuration is reachable only through explicit initialization import or `llmops migrate-config`.
- [x] No agent is privileged by core code or examples.
- [x] Deployment bundles contain no secrets, `.env` files, model weights, logs, state databases, tests, or private topology.
- [x] Dirty deployment and obsolete generated source paths are refused.
- [x] Fresh install, upgrade, repair, rollback, uninstall, and purge pass under isolated roots on both macOS hosts.
- [x] Clean-archive proxy execution works without an ignored wrapper.
- [x] All Markdown links resolve and public files contain no private machine defaults.
- [x] `scripts/precheck --release` passes from a committed clean source tree.
- [x] Release notes describe configuration changes, migration, upgrade, rollback, and uninstall.
- [ ] Two operational reporting cycles pass before release tagging.
