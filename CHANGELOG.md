# Changelog

## Unreleased - Operator V1 Release Candidate

- Replaced proof-of-concept shell configuration with canonical JSON profiles, inventories, services, and dependency-aware stacks.
- Added independent component lifecycle operations, coordinated stack operations, immutable multi-host deployment, drift detection, and atomic rollback.
- Added transactional guided initialization with selective reuse and normalization of existing model profiles.
- Added classified one-way migration for legacy model, service, agent, and inventory inputs.
- Added read-only host probing for SSH, executables, Python, model paths, launchd, ports, architecture, and memory.
- Removed repository synchronization, privileged agent adapters, ignored runtime wrappers, private topology, and obsolete internal procedures.
- Added clean-archive installation, migration, privacy, documentation, and macOS release checks.

## Pre-release History

Earlier commits document the exploratory model runners, proxy tap, TTS bridge, and deployment experiments that led to operator v1. Those proof-of-concept interfaces are not supported by this release.
