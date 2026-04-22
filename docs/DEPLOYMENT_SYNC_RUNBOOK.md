# Deployment + Sync Runbook

**Created**: 2026-02-24
**Updated**: 2026-04-17

- [Deployment + Sync Runbook](#deployment--sync-runbook)
  - [Purpose](#purpose)
  - [Phase 1 Workflow](#phase-1-workflow)
  - [1) Deploy with One Command](#1-deploy-with-one-command)
  - [2) Internal Helper Stages](#2-internal-helper-stages)
  - [4) What Gets Installed](#4-what-gets-installed)
  - [5) What Is Explicitly Out of Scope](#5-what-is-explicitly-out-of-scope)
  - [6) Optional Runtime Venv + Secrets-Kit](#6-optional-runtime-venv--secrets-kit)
  - [7) Verification and Audit](#7-verification-and-audit)
  - [8) Legacy Repo Sync Path](#8-legacy-repo-sync-path)

## Purpose

Deploy `LLM-Ops-Kit` as a staged runtime payload over SSH/rsync without syncing the full git checkout to the target host as the primary workflow.

Phase 1 is intentionally narrow:

- one local admin machine
- one selected deployment config per push
- one-way sync only
- target runtime owned by the target user
- no `.openclaw` distribution
- no secrets in the staged payload

## Phase 1 Workflow

The staged deployment flow is:

1. clone or update the repo locally
2. create or update a local deployment config
3. build a staged virtual target filesystem locally
4. push only that staged payload to one or more target hosts from that config
5. run remote link/venv/verification checks on the deployed target

## 1) Deploy with One Command

Interactive deploy:

```bash
./build-stage -c default
```

Verbose deploy:

```bash
./build-stage -c default -v
```

Non-interactive deploy with an existing config:

```bash
./build-stage -c default -y
```

Dry run:

```bash
./build-stage -c default --dry-run
```

This uses a local-only config file at:

```text
./stage/deploy_config/default.env
```

The deployment config stays on the admin machine. It is not pushed to remote hosts.

`build-stage` will:

1. create or update the named config if it is missing or if `-n` / `-d` is passed
2. show the deployment plan
3. ask for confirmation unless `-y` is used
4. build `./stage/<config-name>/` as a virtual remote filesystem
5. sync the staged install tree and staged bin tree to each configured host over SSH/rsync
6. create or validate the configured runtime venv on the remote host
7. deploy managed links into the configured bin dir
8. verify the managed runtime surface on the target host

Push logs are written locally under:

```text
./stage/deploy_config/logs/<config-name>/
```

## 2) Internal Helper Stages

`build-stage` shells into `scripts/deploy-runtime`, which orchestrates these internal helper commands:

- `scripts/setup-deploy`: creates or overlays a named config file in `stage/deploy_config/`
- `scripts/stage-runtime`: builds the staged virtual target filesystem in `stage/<config-name>/`
- `scripts/push-runtime`: syncs the staged install/bin trees and runs remote post-deploy validation

You can still run them directly for troubleshooting, but `build-stage` is the intended repo-root operator entrypoint.

## 4) What Gets Installed

Phase 1 deployment manages exactly two target surfaces:

- install root, default `~/.llm-ops`
- managed command links, default `~/bin`

The installed runtime remains relocatable by config:

- install prefix is configurable per config
- bin dir is configurable per config
- runtime state file is configurable per config

## 5) What Is Explicitly Out of Scope

These are not distributed by the Phase 1 deploy flow:

- `~/.openclaw`
- OpenClaw sessions, logs, or app-local config trees
- secrets
- arbitrary home-directory files

Remote config, logs, run state, and backups under the runtime root are preserved by default.

## 6) Optional Runtime Venv + Secrets-Kit

Deployment configs may configure a runtime venv path. When provided, post-deploy validation will:

- create the venv if missing
- record it in runtime state
- prepend its `bin/` directory to `PATH` for toolkit wrappers

Profiles may also optionally request `Secrets-Kit` installation into that same venv.

That integration remains optional. `Secrets-Kit` distribution is still treated as a separate project concern.

## 7) Verification and Audit

Before final release:

- verify staged payload contents are correct
- verify managed links resolve to the installed runtime
- confirm `stage/` is not tracked
- confirm docs match the staged deployment workflow
- run the release checklist in [RELEASE_AUDIT_CHECKLIST](./RELEASE_AUDIT_CHECKLIST.md)

## 8) Legacy Repo Sync Path

`sync-ops-scripts` remains available as a legacy repo-sync helper for existing operator flows.

It is no longer the primary documented deployment path for Phase 1.
