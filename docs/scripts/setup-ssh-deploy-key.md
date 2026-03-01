# setup-ssh-deploy-key

**Created**: 2026-02-28
**Updated**: 2026-02-28

## Purpose

Create/load a deploy SSH key with TTL and optionally install the public key on a remote host.

## Syntax

```bash
~/projects/OpenClaw-Ops-Toolkit/scripts/setup-ssh-deploy-key.sh [options]
```

## Examples

```bash
# Create/load key only
~/projects/OpenClaw-Ops-Toolkit/scripts/setup-ssh-deploy-key.sh

# Create/load key and install to remote
~/projects/OpenClaw-Ops-Toolkit/scripts/setup-ssh-deploy-key.sh \
  --host <host> --user <user> --install-remote
```

## Notes

- Uses `ssh-agent` + `ssh-add -t` for short-lived key loading.
- Does not delete existing keys.
- Prints verification and cleanup commands at the end.

