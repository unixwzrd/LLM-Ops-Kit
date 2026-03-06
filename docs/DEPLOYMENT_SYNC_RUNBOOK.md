# Deployment + Sync Runbook

**Created**: 2026-02-24
**Updated**: 2026-03-03

- [Deployment + Sync Runbook](#deployment--sync-runbook)
  - [Purpose](#purpose)
  - [Preconditions](#preconditions)
  - [1) Sync Code](#1-sync-code)
  - [2) Runtime Link Manifest](#2-runtime-link-manifest)
  - [3) Deploy Runtime Links on Remote](#3-deploy-runtime-links-on-remote)
  - [4) Verify Runtime Links on Remote](#4-verify-runtime-links-on-remote)
  - [5) Runtime Commands (Action-Based)](#5-runtime-commands-action-based)
  - [6) Key Notes](#6-key-notes)
  - [7) SSH Agent Safety](#7-ssh-agent-safety)
  - [8) Troubleshooting](#8-troubleshooting)
    - [A) `declare -A: invalid option`](#a-declare--a-invalid-option)
    - [B) `mkpath: Operation not supported`](#b-mkpath-operation-not-supported)
    - [C) Password prompts unexpectedly](#c-password-prompts-unexpectedly)
  - [9) Post-Compaction Audit Drift Check](#9-post-compaction-audit-drift-check)

## Purpose

Deploy `LLM-Ops-Kit` changes safely to another host and keep runtime commands consistent using user-local links (`$HOME/bin`) only.

## Preconditions

- Source repo: `~/projects/LLM-Ops-Kit`
- Remote repo path target: `~/projects/LLM-Ops-Kit`
- Remote host reachable via SSH
- Remote has `/usr/local/bin/bash` (for scripts using bash features beyond macOS default bash 3)

## 1) Sync Code

From local machine (recommended, one command):

```bash
~/bin/sync-ops-scripts --delete
```

This now performs:

1. Manifest refresh (`scripts/generate-manifest`)
2. `rsync` transfer
3. Remote link deploy (`deploy-runtime-links.sh`)
4. Remote link verify (`verify-runtime-links.sh`)

Equivalent explicit form:

```bash
rsync -avz --delete ~/projects/LLM-Ops-Kit/ <host>:~/projects/LLM-Ops-Kit/
```

If you only want transfer (skip deploy+verify):

```bash
~/bin/sync-ops-scripts --delete --no-links
```

## 2) Runtime Link Manifest

Link definitions are now centralized in:

`~/projects/LLM-Ops-Kit/scripts/runtime-links.manifest`

The manifest is auto-generated from launcher symlinks via `scripts/generate-manifest` (also run by `sync-ops-scripts`). Deploy and verify consume this file.

## 3) Deploy Runtime Links on Remote

Use explicit remote bash path:

```bash
ssh <host> '/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/deploy-runtime-links.sh'
```

## 4) Verify Runtime Links on Remote

```bash
ssh <host> '/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/verify-runtime-links.sh'
```

## 5) Runtime Commands (Action-Based)

All commands are extensionless and action-driven.

```bash
~/bin/gateway [start|stop|restart|status]
~/bin/proxy [start|stop|restart|status]
~/bin/tts-bridge [start|stop|restart|status]
~/bin/Qwen3 [start|stop|restart|status]
~/bin/Qwen3.5 [start|stop|restart|status]
~/bin/BGEen [start|stop|restart|status]
~/bin/openclaw-stack [start|stop|restart|status] [all|gateway|llm|embedding|proxy|models]
~/bin/openclaw-report
```

Typical bring-up order:

```bash
~/bin/gateway start
~/bin/Qwen3 start
~/bin/proxy start
# Start embedding only if needed
~/bin/BGEen start
```

## 6) Key Notes

- Link management is intentionally limited to `$HOME/bin` for host portability.
- No `/Volumes/...` assumptions in deploy/verify scripts.
- If remote default bash is too old, run scripts with `/usr/local/bin/bash` explicitly.

## 7) SSH Agent Safety

Load deploy key for short window only:

```bash
eval "$(ssh-agent -s)"
ssh-add -t 20m ~/.ssh/id_ed25519_misfour_deploy
```

After deploy:

```bash
ssh-add -d ~/.ssh/id_ed25519_misfour_deploy
# or clear all
ssh-add -D
```

## 8) Troubleshooting

### A) `declare -A: invalid option`

Run scripts with remote bash 5:

```bash
ssh <host> '/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/verify-runtime-links.sh'
```

### B) `mkpath: Operation not supported`

Destination path is invalid for that host. Use home-relative target:

```bash
<host>:~/projects/LLM-Ops-Kit/
```

### C) Password prompts unexpectedly

New shell likely missing loaded key. Re-run `ssh-agent` + `ssh-add` with TTL.

## 9) Post-Compaction Audit Drift Check

If OpenClaw injects a warning like `Post-Compaction Audit`, extract the missing required startup-file patterns from logs:

```bash
# Gateway log (canonical)
rg -n "Post-Compaction Audit|required startup files were not read|  - " ~/.openclaw/logs/gateway.log

# Rendered proxy prompt/response stream (optional)
rg -n "Post-Compaction Audit|required startup files were not read|  - " ~/.llmops/logs/openai-proxy.rendered.log

# Compact view: only missing file/pattern lines
rg -n "Post-Compaction Audit|required startup files were not read|  - " ~/.openclaw/logs/gateway.log \
  | sed -n '/Post-Compaction Audit/,+6p'
```

Current OpenClaw runtime default required reads (as of 2026-02-27) include:

- `WORKFLOW_AUTO.md`
- `memory/\\d{4}-\\d{2}-\\d{2}\\.md`

Recommended compatibility fix:

- Keep a lightweight `~/OpenClaw-workspace/WORKFLOW_AUTO.md` stub so compaction audits do not spam chat.
