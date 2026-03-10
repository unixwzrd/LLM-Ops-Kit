# install-runtime

**Created**: 2026-03-03
**Updated**: 2026-03-10

Install a durable runtime payload outside your git checkout, then link commands from `~/bin`.

```bash
~/bin/install-runtime [--source <repo-path>] [--prefix <install-base>] [--bin-dir <bin-dir>] [--state-file <path>] [--no-links]
```

Default install path:

- `~/.llm-ops/current`

Default runtime state file:

- `~/.llm-ops/runtime-state.env`

Default command link path:

- `~/bin`

What gets installed:

- `scripts/` -> `~/.llm-ops/current/scripts/`
- `bin/` -> `~/.llm-ops/current/bin/`

What gets linked:

- managed commands in `~/bin`, based on `scripts/runtime-links.manifest`
- those links point at the installed runtime under `~/.llm-ops/current`, not back to the git checkout

This is useful when you do not want runtime commands to break if `~/projects/LLM-Ops-Kit` is moved or deleted.
