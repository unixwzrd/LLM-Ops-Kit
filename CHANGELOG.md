# Changelog

## Operator V1 Release Candidate

### Configuration and migration

- Replaced proof-of-concept shell configuration with canonical JSON profiles, inventories, services, and dependency-aware stacks.
- Added transactional guided initialization with selective reuse and normalization of existing model profiles.
- Added classified one-way migration for legacy model, service, agent, and inventory inputs without retaining runtime compatibility reads.
- Added read-only host probing for SSH, executables, Python, model paths, launchd, ports, architecture, and memory.

### Lifecycle and multi-host operation

- Added independent component lifecycle operations and dependency-aware stack composition with non-mutating plans, readiness checks, idempotence, cascade behavior, and partial-start rollback.
- Added immutable multi-host deployment, role-filtered runtime configuration, complete sanitized topology catalogs, drift detection, and atomic rollback.
- Added aggregate `llmops status`, trusted peer host operations over SSH, absolute remote command paths, and explicit `authority-only` status for components intentionally observable only from the desired-state authority.
- Added component help descriptions and agent-neutral profiles without privileged Hermes or OpenClaw behavior.

### Installation and updates

- Added a runtime-only `.tar.xz` release artifact with a per-file manifest and external SHA-256 checksum.
- Added a separately checksummed bootstrap installer for repository-free installation.
- Added `llmops update` check, plan, JSON, verified local apply, and offline artifact workflows.
- Added clean-archive fresh-install, upgrade, repair, rollback, uninstall, purge, migration, privacy, documentation, and macOS release checks.
- Excluded tests, migration fixtures, private topology, and maintainer-only release tooling from installed runtime payloads.
- Made maintainer prechecks honor `PYTHON_BIN` so the complete suite can run against an explicitly selected Conda, venv, virtualenv, or uv interpreter instead of the host's incidental `python3`.

### Models, proxy, and logging

- Centralized model log rotation using copy-and-truncate so active log paths and inodes remain stable for monitoring tools.
- Kept model-proxy strictly passive: diagnostic prompt rendering never changes the request forwarded upstream.
- Added Hugging Face-compatible `raise_exception` support to model-proxy chat-template rendering, with regressions against the shipped Qwen template.
- Added an optional Qwen template derived from the unchanged stock template that removes historical image, audio, and video payloads while retaining the latest payload of each media type.
- Added focused regressions for historical tool exchanges, duplicate embedded payloads, and structured image and video content.

### Cleanup and documentation

- Removed repository synchronization, post-commit synchronization, ignored runtime wrappers, embedded Python in shell scripts, private machine defaults, and obsolete internal procedures.
- Replaced generated ignore rules with a project-specific `.gitignore` and removed repository-local staging and temporary artifacts.
- Rewrote operator documentation for the final `llmops` command surface, clean installation, migration, configuration, proxy diagnostics, upgrades, rollback, and uninstall.

## Pre-release History

Earlier commits document the exploratory model runners, proxy tap, TTS bridge, and deployment experiments that led to operator v1. Those proof-of-concept interfaces are not supported by this release.
