# Troubleshooting

**Created**: 2026-02-26
**Updated**: 2026-02-26


## Link verification shows `MISSING`

Symptoms:
- `verify-runtime-links.sh` reports missing symlink(s).

Fix:
```bash
/usr/local/bin/bash ~/projects/agent-work/scripts/deploy-runtime-links.sh
/usr/local/bin/bash ~/projects/agent-work/scripts/verify-runtime-links.sh
```

## `declare -A: invalid option`

Cause:
- Script executed under bash 3.x.

Fix:
```bash
/usr/local/bin/bash ~/projects/agent-work/scripts/<script>.sh
```

## `mkpath: Operation not supported`

Cause:
- Invalid remote target path.

Fix:
- Use home-relative destination: `~/projects/agent-work`.

## Model reports started but behaves stale

Checks:
```bash
~/bin/Qwen3 status
~/bin/BGEen status
~/bin/openclaw-stack status
```

Then restart target cleanly:
```bash
~/bin/Qwen3 restart
~/bin/BGEen restart
```

## Embedding indexing context-size errors

Symptoms:
- Errors around token/context limits from embedding model.

Actions:
- Verify embedding profile settings with `~/bin/BGEen settings`.
- Confirm running model actually supports the configured `CTX_SIZE`.
- Check OpenClaw memory chunking values in `.openclaw/openclaw.json`.

## SSH keeps prompting for password

Checks:
- `ssh-add -l` shows key loaded.
- `~/.ssh/authorized_keys` on remote contains your public key.
- remote permissions: `~/.ssh` 700, `authorized_keys` 600.
