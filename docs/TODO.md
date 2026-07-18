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
  - Soak restarted at 2026-07-17 15:51 CDT after the Qwen3TTS process crashed. The bridge remained available and correctly reported upstream failure; the TTS model was restored and end-to-end generation passed.
  - Soak restarted again at 2026-07-17 20:15 CDT after deploying the latest-image Qwen template and strictly passive model proxy. The prior Qwen3TTS failure was traced to an uncaught Metal `kIOGPUCommandBufferCallbackErrorImpactingInteractivity` error.
  - Soak restarted at 2026-07-17 20:45 CDT after refining the Jinja template to remove complete historical image tool exchanges while retaining only the final image. Both hosts deployed runtime `operator-v1-rc-e9c427f`, all configured components returned to running state, and deployment drift was zero.
  - Soak restarted at 2026-07-17 21:00 CDT after deploying trusted peer control and restarting Qwen3.6 from the agent host and model-proxy from the model host. Both components passed readiness checks and runtime `operator-v1-rc-3020dee` had zero deployment drift.
  - Soak restarted at 2026-07-17 21:04 CDT after deploying centralized copy-and-truncate model log rotation. A live Qwen3.6 restart preserved active log inode `917783407`, archived the prior contents, and returned to API-ready state on runtime `operator-v1-rc-ba0da59`.
- [ ] Obtain a green macOS CI run after the release candidate is pushed for review.

## General-User Distribution Gate

- [x] Produce a versioned, checksum-verified release artifact containing only installed runtime files. Installation and upgrade do not require a Git checkout or depend on the checkout location.
- [x] Add a repository-free bootstrap installer that downloads a selected GitHub release, verifies it, installs only the required components, and reports exact recovery steps without piping an unverified response directly into a privileged shell.
- [ ] Add `llmops update` with local and remote version discovery, release selection, plan and JSON output, atomic apply, rollback, and handling for an older control command on either side of an SSH connection.
  - [x] Local check, plan, JSON output, verified apply, immutable previous-release retention, and offline artifact operation.
  - [ ] Remote discovery, older-peer bootstrap, coordinated host selection, and remote rollback reporting.
- [ ] Add one application-owned Python runtime environment with a checksum-verified uv or `venv` bootstrap, offline/error handling, dependency locking, repair, upgrade, rollback, and purge semantics. Python-backed launchd services should use its explicit interpreter path without sourcing interactive shell profiles.
- [x] Add portable read-only observer snapshots so any trusted configured host can run global `llmops status` without receiving mutation authority or secret material.
- [x] Add explicit trusted-control snapshots and `llmops host` operations for approved operator hosts. Remote execution uses the configured absolute `llmops` path over SSH, permits only restricted LLM-Ops-Kit command families, and does not depend on login-shell startup files.
- [x] Distribute a complete sanitized topology catalog to managed hosts while retaining role-filtered runtime profiles. Synchronization is one-way from the desired-state authority, checksummed, and atomic.
- [ ] Validate identical catalog hashes and global status from both live hosts after the soak and release-candidate deployment.
  - Current pre-soak evidence: both hosts have catalog SHA-256 `fea1c33572fb3a39bc056d50c1bb25cbd34fae8d5278fe39e8b44fc5e9dd2bec` and return identical status for all model-host and agent-host components.
  - The Desktop tunnel remains unobservable from managed peers because it runs in the desktop user's launchd domain and the service account has no SSH authorization to that account. Do not expand primary-account access implicitly; either keep this component authority-only or approve a separate least-privilege observer mechanism.
- [ ] Make configuration and toolkit-version drift visible from every trusted control host. Refuse automatic merging of independently edited host configuration and provide an explicit reconciliation workflow.
- [ ] Package an agent-neutral LLM-Ops-Kit skill that uses `doctor`, `plan`, `status`, and JSON output for setup and operations while requiring explicit approval for mutations and SSH provisioning.

## Post-V1

- [ ] Add a typed MLXForge engine driver so model lifecycle and health checks can migrate from llama.cpp without changing stack or component interfaces.
- [ ] Evaluate an optional Textual TUI or loopback-only static web console for guided inventory, profile, dependency, and status management. It must consume the existing control/JSON interfaces rather than implement another orchestration path.
- [ ] Integrate Secrets-Kit only through explicit provider references after its release contract stabilizes.
- [ ] Remove plaintext `.env` secret injection after the external provider path is validated.
- [ ] Add signed release manifests if distribution expands beyond a trusted LAN.
- [ ] Consider guided model downloads only as a separately approved feature.
- [ ] Add an explicit per-component restart policy and supervisor integration. Keep automatic restart disabled by default for high-memory model processes.
