# Release Audit

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

- [ ] Public commands match `README.md` and `llmops --help`.
- [ ] Canonical configuration is JSON-only at runtime.
- [ ] Legacy configuration is reachable only through `llmops migrate-config`.
- [ ] No agent is privileged by core code or examples.
- [ ] Deployment bundles contain no secrets, `.env` files, model weights, logs, state databases, tests, or private topology.
- [ ] Dirty deployment is refused unless explicitly allowed and recorded.
- [ ] Fresh install, upgrade, repair, rollback, uninstall, and purge pass on clean macOS accounts.
- [ ] All Markdown links resolve.
- [ ] `scripts/precheck` passes from a clean checkout.
- [ ] Release notes describe schema or migration changes and exact rollback procedure.
