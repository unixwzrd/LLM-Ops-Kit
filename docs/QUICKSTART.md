# Quickstart (10 Minutes)

**Created**: 2026-02-26
**Updated**: 2026-03-03

- [Quickstart (10 Minutes)](#quickstart-10-minutes)
  - [Requirements](#requirements)
  - [Local bring-up](#local-bring-up)
  - [Remote sync + deploy](#remote-sync--deploy)
  - [Common checks](#common-checks)

## Requirements

- OpenClaw installed
- `llama-server` at `/usr/local/bin/llama-server`
- Bash 4+ available as `/usr/local/bin/bash` on remote hosts
- `ssh`, `rsync`, `jq`

See `docs/CONFIGURATION.md` for environment overrides before first run.

## Local bring-up

```bash
/usr/local/bin/bash ~/projects/OpenClaw-Ops-Toolkit/scripts/deploy-runtime-links.sh
/usr/local/bin/bash ~/projects/OpenClaw-Ops-Toolkit/scripts/verify-runtime-links.sh
~/bin/gateway start
~/bin/Qwen3 start
~/bin/BGEen start
~/bin/proxy start
# Optional for local OpenAI-style TTS via MLX bridge:
# ~/bin/Qwen3TTS start
# ~/bin/tts-bridge start
```

## Remote sync + deploy

```bash
~/bin/sync-ops-scripts --delete
ssh <host> '/usr/local/bin/bash ~/projects/OpenClaw-Ops-Toolkit/scripts/deploy-runtime-links.sh'
ssh <host> '/usr/local/bin/bash ~/projects/OpenClaw-Ops-Toolkit/scripts/verify-runtime-links.sh'
```

## Common checks

```bash
~/bin/openclaw-stack status
~/bin/Qwen3 settings
~/bin/BGEen settings
```

If anything looks off, go to `docs/TROUBLESHOOTING.md`.
