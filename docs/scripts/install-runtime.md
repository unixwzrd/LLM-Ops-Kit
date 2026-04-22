# install-runtime

**Created**: 2026-03-03
**Updated**: 2026-04-17

Legacy helper for installing a durable runtime payload outside your git checkout, then linking commands from `~/bin`.

Legacy first-time install:

```bash
git clone https://github.com/unixwzrd/LLM-Ops-Kit.git ~/projects/LLM-Ops-Kit
cd ~/projects/LLM-Ops-Kit
./scripts/install-runtime --source "$PWD"
```

```bash
~/bin/install-runtime [--source <repo-or-stage-path>] [--prefix <install-base>] [--bin-dir <bin-dir>] [--state-file <path>] [--venv-path <path>] [--install-secrets-kit] [--secrets-kit-source <spec>] [--no-links]
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

Current Phase 1 staged deploy note:

- staged SSH deployment now uses `build-stage` / `deploy-runtime` and `push-runtime` as the primary path
- `install-runtime.sh` remains for compatibility and local repair workflows
- `--venv-path` optionally creates or reuses a dedicated runtime Python virtualenv
- the installer records that venv path in the runtime state file so toolkit wrappers can prepend it to `PATH`
- `--install-secrets-kit` optionally installs `Secrets-Kit` into that same runtime venv
