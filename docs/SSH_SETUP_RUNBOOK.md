# SSH Setup Runbook

**Created**: 2026-02-26
**Updated**: 2026-02-26

- [SSH Setup Runbook](#ssh-setup-runbook)
  - [Goal](#goal)
  - [1) Create a dedicated deploy key (local)](#1-create-a-dedicated-deploy-key-local)
  - [2) Load key with TTL](#2-load-key-with-ttl)
  - [3) Install public key on remote](#3-install-public-key-on-remote)
  - [4) Verify key auth](#4-verify-key-auth)
  - [5) Deploy + verify runtime links (remote bash 5)](#5-deploy--verify-runtime-links-remote-bash-5)
  - [6) Remove key from agent after deployment](#6-remove-key-from-agent-after-deployment)
  - [Troubleshooting](#troubleshooting)

## Goal

Set up secure SSH-based deployment for `OpenClaw-Ops-Kit` using short-lived agent credentials.

## 1) Create a dedicated deploy key (local)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_misfour_deploy -C "misfour-deploy"
chmod 600 ~/.ssh/id_ed25519_misfour_deploy
chmod 644 ~/.ssh/id_ed25519_misfour_deploy.pub
```

## 2) Load key with TTL

```bash
eval "$(ssh-agent -s)"
ssh-add -t 20m ~/.ssh/id_ed25519_misfour_deploy
ssh-add -l
```

## 3) Install public key on remote

```bash
ssh-copy-id -i ~/.ssh/id_ed25519_misfour_deploy.pub <user>@<host>
```

If `ssh-copy-id` is unavailable, append key manually:

```bash
cat ~/.ssh/id_ed25519_misfour_deploy.pub | ssh <user>@<host> 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

## 4) Verify key auth

```bash
ssh <host> 'echo SSH_OK'
```

## 5) Deploy + verify runtime links (remote bash 5)

```bash
ssh <host> '/usr/local/bin/bash ~/projects/agent-work/scripts/deploy-runtime-links.sh'
ssh <host> '/usr/local/bin/bash ~/projects/agent-work/scripts/verify-runtime-links.sh'
```

## 6) Remove key from agent after deployment

```bash
ssh-add -d ~/.ssh/id_ed25519_misfour_deploy
# or clear all loaded keys
ssh-add -D
```

## Troubleshooting

- `declare -A: invalid option`: run scripts with `/usr/local/bin/bash`.
- Password prompts persist: verify `authorized_keys` ownership/permissions and correct remote username.
- `mkpath: Operation not supported`: target path invalid on remote; use `~/projects/agent-work`.
