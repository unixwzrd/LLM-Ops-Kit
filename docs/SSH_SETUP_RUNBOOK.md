# SSH Setup Runbook

**Created**: 2026-02-26
**Updated**: 2026-02-28

- [SSH Setup Runbook](#ssh-setup-runbook)
  - [Goal](#goal)
  - [Related Docs](#related-docs)
  - [Fast Path Script](#fast-path-script)
  - [Web UI SSH Tunnel](#web-ui-ssh-tunnel)
  - [1) Create a dedicated deploy key (local)](#1-create-a-dedicated-deploy-key-local)
  - [2) Load key with TTL](#2-load-key-with-ttl)
  - [3) Install public key on remote](#3-install-public-key-on-remote)
  - [4) Verify key auth](#4-verify-key-auth)
  - [5) Deploy + verify runtime links (remote bash 5)](#5-deploy--verify-runtime-links-remote-bash-5)
  - [6) Remove key from agent after deployment](#6-remove-key-from-agent-after-deployment)
  - [Troubleshooting](#troubleshooting)

## Goal

Set up secure SSH-based deployment for `LLM-Ops-Kit` using short-lived agent credentials.

## Related Docs

- Main index: [`../README.md`](../README.md)
- Configuration: [`CONFIGURATION.md`](./CONFIGURATION.md)
- Deployment flow: [`DEPLOYMENT_SYNC_RUNBOOK.md`](./DEPLOYMENT_SYNC_RUNBOOK.md)

## Fast Path Script

Use the helper script for key creation/load and optional remote key install:

```bash
~/projects/LLM-Ops-Kit/scripts/setup-ssh-deploy-key.sh --help
~/projects/LLM-Ops-Kit/scripts/setup-ssh-deploy-key.sh --host <host> --user <user> --install-remote
```

## Web UI SSH Tunnel

To access a remote OpenClaw web UI running on `127.0.0.1:18789`, forward it to your local machine:

```bash
ssh -L 18789:127.0.0.1:18789 <user>@<host>
```

Then open:

```text
http://127.0.0.1:18789
```

Operator-local convenience alias example:

```bash
alias oc_vm='ssh -L 18789:127.0.0.1:18789 unixwzrd@10.0.0.202'
```

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
ssh <host> '/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/deploy-runtime-links.sh'
ssh <host> '/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/verify-runtime-links.sh'
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
- `mkpath: Operation not supported`: target path invalid on remote; use `~/projects/LLM-Ops-Kit`.
