# Troubleshooting

Back: [docs/INDEX.md](./INDEX.md)

**Created**: 2026-02-26
**Updated**: 2026-03-01

- [Troubleshooting](#troubleshooting)
  - [Interpreter policy](#interpreter-policy)
  - [Link verification shows `MISSING`](#link-verification-shows-missing)
  - [Deploy reports `CONFLICT` after repo rename](#deploy-reports-conflict-after-repo-rename)
  - [`declare -A: invalid option`](#declare--a-invalid-option)
  - [`mkpath: Operation not supported`](#mkpath-operation-not-supported)
  - [Model reports started but behaves stale](#model-reports-started-but-behaves-stale)
  - [Embedding indexing context-size errors](#embedding-indexing-context-size-errors)
  - [SSH keeps prompting for password](#ssh-keeps-prompting-for-password)


## Interpreter policy

- Bash scripts use `#!/usr/bin/env bash` and are written for Bash 3.2+ compatibility.
- Python helper scripts use `#!/usr/bin/env python` and require Python 3.9+.
- Bash 5+ is recommended, but not required for normal operation.

## Link verification shows `MISSING`

Symptoms:

- `verify-runtime-links.sh` reports missing symlink(s).

Fix:

```bash
/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/deploy-runtime-links.sh
/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/verify-runtime-links.sh
```

## Deploy reports `CONFLICT` after repo rename

Symptoms:

- `deploy-runtime-links.sh` reports conflicts where links still point at `~/projects/OpenClaw-Ops-Toolkit/...`.

Fix:

```bash
/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/deploy-runtime-links.sh
/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/verify-runtime-links.sh
```

Notes:

- Deploy auto-heals symlinks from `OpenClaw-Ops-Toolkit` to `LLM-Ops-Kit` for managed runtime commands.
- Non-symlink files in `~/bin` are still treated as real conflicts and are not overwritten automatically.

## `declare -A: invalid option`

Cause:

- Script executed under bash 3.x.

Fix:

```bash
/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/<script>.sh
```

## `mkpath: Operation not supported`

Cause:

- Invalid remote target path.

Fix:

- Use home-relative destination: `~/projects/LLM-Ops-Kit`.

## Model reports started but behaves stale

Checks:

```bash
~/bin/modelctl status
~/bin/Qwen3 status
~/bin/BGEm3 status
```

Then restart target cleanly:

```bash
~/bin/Qwen3 restart
~/bin/BGEm3 restart
```

## Embedding indexing context-size errors

Symptoms:

- Errors around token/context limits from embedding model.

Actions:

- Verify embedding profile settings with `~/bin/BGEm3 settings`.
- Confirm running model actually supports the configured `CTX_SIZE`.
- Check OpenClaw memory chunking values in `.openclaw/openclaw.json`.

## SSH keeps prompting for password

Checks:

- `ssh-add -l` shows key loaded.
- `~/.ssh/authorized_keys` on remote contains your public key.
- remote permissions: `~/.ssh` 700, `authorized_keys` 600.

## See Also

- [Quickstart](./QUICKSTART.md)
- [Configuration](./CONFIGURATION.md)
- [How It Works](./HOW_IT_WORKS.md)
