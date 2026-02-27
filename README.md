# OpenClaw-Ops-Kit

**Created**: 2026-02-20
**Updated**: 2026-02-26


Operational toolkit for running, deploying, and maintaining a local OpenClaw stack across hosts.

![OpenClaw Ops Kit](docs/images/OpenClaw-Ops-Kit-Banner.png)

[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-informational)](#) [![Shell](https://img.shields.io/badge/Shell-bash-blue)](#) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

- [OpenClaw-Ops-Kit](#openclaw-ops-kit)
  - [Why This Repo Exists](#why-this-repo-exists)
  - [Requirements](#requirements)
  - [Quick Start](#quick-start)
  - [Runtime Command Surface](#runtime-command-surface)
  - [Link Management (Single Source of Truth)](#link-management-single-source-of-truth)
  - [Model Profiles](#model-profiles)
  - [Packaging Status](#packaging-status)
  - [Documentation Map](#documentation-map)
  - [Repository Scope](#repository-scope)
  - [Contributing](#contributing)
  - [Support This Work](#support-this-work)
  - [Contact](#contact)
  - [License](#license)


## Why This Repo Exists

`OpenClaw-Ops-Kit` is the operator layer around a local OpenClaw install:

- Unified startup/shutdown/status scripts for gateway, proxy, LLM, and embeddings
- Model profile management (`Qwen3`, `Qwen3.5`, `BGEen`) via one launcher architecture
- Deployment helpers for cross-host sync and runtime link management
- Practical runbooks and changelog-driven operations
- Prompt/template and observability tooling for debugging real runtime behavior

This repo is intentionally focused on **operations and reproducibility**, not raw app source.

## Requirements

- OpenClaw installed and configured on the host
- `llama.cpp` server binary available at `/usr/local/bin/llama-server`
- Bash 4+ for some scripts (remote usage may require `/usr/local/bin/bash`)
- Standard CLI tools: `ssh`, `rsync`, `jq`, `sed`, `awk`, `perl`
- Python 3.9+ only where optional Python helpers are used

## Quick Start

```bash
# 1) Sync repo to target host (if needed)
~/bin/sync-agent-work --delete

# 2) Deploy runtime commands into ~/bin
/usr/local/bin/bash ~/projects/agent-work/scripts/deploy-runtime-links.sh

# 3) Verify links
/usr/local/bin/bash ~/projects/agent-work/scripts/verify-runtime-links.sh

# 4) Start services
~/bin/gateway start
~/bin/Qwen3 start
~/bin/BGEen start
~/bin/proxy start
```

## Runtime Command Surface

```bash
~/bin/gateway [start|stop|restart|status]
~/bin/proxy [start|stop|restart|status]
~/bin/Qwen3 [start|stop|restart|status|settings]
~/bin/Qwen3.5 [start|stop|restart|status|settings]
~/bin/BGEen [start|stop|restart|status|settings]
~/bin/openclaw-stack [start|stop|restart|status] [all|gateway|llm|embedding|proxy|models]
~/bin/openclaw-report
```

## Link Management (Single Source of Truth)

Runtime link mappings are centralized in:

- `scripts/runtime-links.manifest`

Both scripts consume this same manifest:

- `scripts/deploy-runtime-links.sh`
- `scripts/verify-runtime-links.sh`

New model launchers are discovered from `scripts/` symlinks to `modelctl`. Regenerate with `scripts/generate-manifest` (also run automatically by `sync-agent-work`).

## Model Profiles

Model defaults live under:

- `scripts/models/`
- `scripts/defaults/`

Current profiles:

- `Qwen3` (LLM)
- `Qwen3.5` (LLM, preset + template mode support)
- `BGEen` (embeddings)

The launcher resolves profile defaults and prints active runtime settings with:

```bash
~/bin/Qwen3 settings
~/bin/Qwen3.5 settings
~/bin/BGEen settings
```

## Packaging Status

This repo currently ships as script-first operations tooling.

A future optional path is to add `pyproject.toml` and package wrappers for installer-driven deployment (`pipx`/`pip`) while keeping shell scripts as the canonical runtime layer.

## Documentation Map

- [`docs/DEPLOYMENT_SYNC_RUNBOOK.md`](docs/DEPLOYMENT_SYNC_RUNBOOK.md) — sync/deploy/verify workflow
- [`docs/OPERATIONAL_WORKFLOW_PHASE1.md`](docs/OPERATIONAL_WORKFLOW_PHASE1.md) — day-to-day operating workflow
- [`docs/PROXY_TAP_RUNBOOK.md`](docs/PROXY_TAP_RUNBOOK.md) — proxy request/response visibility + jq recipes
- [`docs/CONTEXT_ARCHITECTURE_PLAN.md`](docs/CONTEXT_ARCHITECTURE_PLAN.md) — context routing/system design
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — chronological operational changes
- [`docs/QUICKSTART.md`](docs/QUICKSTART.md) — fast path setup and startup
- [`docs/SSH_SETUP_RUNBOOK.md`](docs/SSH_SETUP_RUNBOOK.md) — SSH key setup and deployment auth flow
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — symptom-driven fixes
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — component and runtime flow overview
- [`docs/GLOSSARY.md`](docs/GLOSSARY.md) — core terms used across docs
- [`docs/SAFE_PUBLISH_CHECKLIST.md`](docs/internal/SAFE_PUBLISH_CHECKLIST.md) — pre-publish safety checks
- [`docs/scripts/README.md`](docs/scripts/README.md) — per-command script guides

## Repository Scope

This repo is safe to publish as an ops/project artifact.

Keep private runtime state out of this repo (for example: local sessions, secrets, raw `.openclaw` data, private memory files).

## Contributing

Issues and PRs are welcome for:

- script hardening
- cross-platform compatibility
- runbook clarity
- model/profile improvements

## Support This Work

If this project saves you time or helps you run local AI infrastructure more reliably, consider supporting independent development:

- [Patreon](https://patreon.com/unixwzrd)
- [Ko-Fi](https://ko-fi.com/unixwzrd)
- [Buy Me a Coffee](https://buymeacoffee.com/unixwzrd)

## Contact

- [unixwzrd@unixwzrd.ai](mailto:unixwzrd@unixwzrd.ai)

## License

[MIT](LICENSE)
