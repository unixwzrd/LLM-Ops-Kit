# uninstall-runtime

**Created**: 2026-03-03
**Updated**: 2026-05-11

Remove runtime command links created by `install-runtime`, and optionally remove the installed runtime payload.

```bash
llmops uninstall-runtime [--prefix <install-base>] [--bin-dir <bin-dir>] [--public-bin-dir <path>] [--state-file <path>] [--keep-files]
```

Notes:

- By default, this removes links from `~/.local/llm-ops/bin` and deletes:
  - `~/.local/llm-ops/current`
- It also removes `~/.local/bin/llmops` when it points at the installed runtime and `--bin-dir` was not used for a legacy cleanup target.
- Also removes runtime state:
  - `~/.local/state/llm-ops/runtime-state.env`
- Use `--keep-files` to remove links only.
- If the runtime manifest is missing, uninstall removes only command links that
  point into the managed runtime, then removes the requested runtime/state.
- To clean up old managed links from a legacy `~/bin` install without deleting
  the current runtime or public launcher, run `scripts/uninstall-runtime.sh --bin-dir "$HOME/bin" --keep-files`.
