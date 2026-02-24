# Deployment + Sync Runbook

## Purpose

Deploy `agent-work` changes safely to another host and keep runtime commands consistent using user-local links (`$HOME/bin`) only.

## Preconditions

- Source repo: `~/projects/agent-work`
- Remote repo path target: `~/projects/agent-work`
- Remote host reachable via SSH
- Remote has `/usr/local/bin/bash` (for scripts using bash features beyond macOS default bash 3)

## 1) Sync Code

From local machine:

```bash
~/bin/sync-agent-work --delete
```

Equivalent explicit form:

```bash
rsync -avz --delete ~/projects/agent-work/ <host>:~/projects/agent-work/
```

## 2) Deploy Runtime Links on Remote

Use explicit remote bash path:

```bash
ssh <host> '/usr/local/bin/bash ~/projects/agent-work/scripts/deploy-runtime-links.sh'
```

## 3) Verify Runtime Links on Remote

```bash
ssh <host> '/usr/local/bin/bash ~/projects/agent-work/scripts/verify-runtime-links.sh'
```

## 4) Runtime Commands (Action-Based)

All commands are extensionless and action-driven.

```bash
~/bin/gateway [start|stop|restart|status]
~/bin/proxy [start|stop|restart|status]
~/bin/Qwen3 [start|stop|restart|status]
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

## 5) Key Notes

- Link management is intentionally limited to `$HOME/bin` for host portability.
- No `/Volumes/...` assumptions in deploy/verify scripts.
- If remote default bash is too old, run scripts with `/usr/local/bin/bash` explicitly.

## 6) SSH Agent Safety

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

## 7) Troubleshooting

### A) `declare -A: invalid option`
Run scripts with remote bash 5:

```bash
ssh <host> '/usr/local/bin/bash ~/projects/agent-work/scripts/verify-runtime-links.sh'
```

### B) `mkpath: Operation not supported`
Destination path is invalid for that host. Use home-relative target:

```bash
<host>:~/projects/agent-work/
```

### C) Password prompts unexpectedly
New shell likely missing loaded key. Re-run `ssh-agent` + `ssh-add` with TTL.
