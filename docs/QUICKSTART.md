# Quickstart (10 Minutes)

**Created**: 2026-02-26
**Updated**: 2026-02-26


## Requirements

- OpenClaw installed
- `llama-server` at `/usr/local/bin/llama-server`
- Bash 4+ available as `/usr/local/bin/bash` on remote hosts
- `ssh`, `rsync`, `jq`

## Local bring-up

```bash
~/bin/deploy-runtime-links.sh
~/bin/verify-runtime-links.sh
~/bin/gateway start
~/bin/Qwen3 start
~/bin/BGEen start
~/bin/proxy start
```

## Remote sync + deploy

```bash
~/bin/sync-agent-work --delete
ssh <host> '/usr/local/bin/bash ~/projects/agent-work/scripts/deploy-runtime-links.sh'
ssh <host> '/usr/local/bin/bash ~/projects/agent-work/scripts/verify-runtime-links.sh'
```

## Common checks

```bash
~/bin/openclaw-stack status
~/bin/Qwen3 settings
~/bin/BGEen settings
```

If anything looks off, go to `docs/TROUBLESHOOTING.md`.
