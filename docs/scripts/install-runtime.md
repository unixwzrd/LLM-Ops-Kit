# install-runtime

**Created**: 2026-03-03
**Updated**: 2026-03-03

Install a durable runtime payload outside your git checkout, then link commands from `~/bin`.

```bash
~/bin/install-runtime [--source <repo-path>] [--prefix <install-base>] [--bin-dir <bin-dir>] [--state-file <path>] [--no-links]
```

Default install path:

- `~/.openclaw-ops/current`

Default runtime state file:

- `~/.openclaw-ops/runtime-state.env`

This is useful when you do not want runtime commands to break if `~/projects/OpenClaw-Ops-Toolkit` is moved or deleted.
