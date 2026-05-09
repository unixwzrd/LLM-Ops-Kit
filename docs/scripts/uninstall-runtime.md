# uninstall-runtime

**Created**: 2026-03-03
**Updated**: 2026-05-09

Remove runtime command links created by `install-runtime`, and optionally remove the installed runtime payload.

```bash
~/bin/uninstall-runtime [--prefix <install-base>] [--bin-dir <bin-dir>] [--state-file <path>] [--keep-files]
```

Notes:

- By default, this removes links from `~/bin` and deletes:
  - `~/.llm-ops/current`
- Also removes runtime state:
  - `~/.local/state/llm-ops/runtime-state.env`
- Use `--keep-files` to remove links only.
