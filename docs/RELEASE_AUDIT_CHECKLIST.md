# Release Audit

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

- [x] Public commands match `README.md` and `llmops --help`.
- [x] Canonical configuration is JSON-only at runtime.
- [x] Legacy configuration is reachable only through `llmops migrate-config`.
- [x] No agent is privileged by core code or examples.
- [x] Deployment bundles contain no secrets, `.env` files, model weights, logs, state databases, tests, or private topology.
- [x] Dirty deployment is refused unless explicitly allowed and recorded.
- [x] Fresh install, upgrade, repair, rollback, uninstall, and purge pass under isolated roots on both target macOS hosts.
- [x] All Markdown links resolve.
- [x] `scripts/precheck` passes from a clean checkout.
- [x] Release notes describe schema or migration changes and exact rollback procedure.
