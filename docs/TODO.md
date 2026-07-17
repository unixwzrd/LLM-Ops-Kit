# Consolidated TODO

**Created**: 2026-05-10
**Updated**: 2026-07-16

Back: [docs/INDEX.md](./INDEX.md)

This is the canonical maintainer-facing TODO for remaining work after the JSON
config, XDG path, deployment, Secrets Kit, and housekeeping rework.

## Release Readiness

- [ ] Run one end-to-end admin deployment against a disposable or low-risk host.
- [ ] Validate local installed-runtime repair with `scripts/install-runtime.sh`.
- [ ] Validate uninstall/cleanup with `scripts/uninstall-runtime.sh --keep-files` and a full uninstall on a disposable target.
- [ ] Confirm `scripts/precheck` passes on a clean checkout after ignored artifact cleanup.
- [ ] Review `docs/RELEASE_AUDIT_CHECKLIST.md` before tagging or pushing a public release.

## Runtime And Config

- [ ] Finish direct `modelctl` integration with rendered JSON config so shell defaults become thinner over time.
- [ ] Add drift detection for transitional per-model env overrides when shipped profiles gain new settings.
- [ ] Add an opt-in helper to append missing override settings without overwriting user comments or values.
- [ ] Add an operator command that prints effective config sources and values for model, agent, proxy, and TTS wrappers.
- [x] Rework installed runtime layout so `~/.local/llm-ops/current` points to a versioned release directory with code-and-config rollback.

## Deployment

- [ ] Document bootstrap recovery steps for failed or partially configured hosts.
- [x] Add bounded retry for failed transport commands in push/apply workflows.
- [x] Add desired-state drift detection and atomic `current`/`previous` rollback.
- [ ] Complete side-by-side runtime 20 canaries and retain runtime 20 for two successful reporting cycles.
- [ ] Document manual acceptance test steps for admin-to-satellite deployment.
- [ ] Regression-test the existing single-host local install flow after deployment changes.

## Secrets And Agents

- [ ] Keep Secrets Kit optional and limited to explicit `seckit run` launch paths.
- [ ] Decide and document service/account naming conventions for shared Secrets Kit examples.
- [ ] Add explicit shell-tracing warnings to any wrapper docs that discuss secret-bearing runtime launches.
- [ ] Validate launchd-managed OpenClaw with `agentctl launchd-*` and `LLMOPS_USE_SECKIT=1` on a real machine.
- [ ] Remove dependence on plaintext `.env` files as long-term secret sources once external secret-provider validation is stable.

## Documentation

- [x] Keep public docs focused on `README.md`, `docs/INDEX.md`, `docs/QUICKSTART.md`, and `docs/DEPLOYMENT_OVERVIEW.md`.
- [x] Keep historical/internal notes out of the public operator path unless they are promoted into this TODO or current docs.
- [ ] Add minimal copy/paste profile examples for `llm`, `embedding`, and `tts` in `docs/ADDING_MODEL_PROFILE.md`.
- [ ] Add common failure modes to proxy and TTS docs as they are found during real validation.
