# install-runtime

**Created**: 2026-03-03
**Updated**: 2026-05-11

Helper for installing a durable runtime payload outside a git checkout, then
linking commands from `~/.local/llm-ops/bin`.

Manual first-time install:

```bash
git clone https://github.com/unixwzrd/LLM-Ops-Kit.git ~/projects/LLM-Ops-Kit
cd ~/projects/LLM-Ops-Kit
./scripts/install-runtime.sh --source "$PWD"
```

```bash
scripts/install-runtime.sh [--source <repo-or-stage-path>] [--prefix <install-base>] [--bin-dir <bin-dir>] [--public-bin-dir <path>] [--state-file <path>] [--venv-path <path>] [--install-secrets-kit] [--secrets-kit-source <spec>] [--no-links] [--no-shell-profile]
```

Default install path:

- `~/.local/llm-ops/current`

Default runtime state file:

- `~/.local/state/llm-ops/runtime-state.env`

Default command link path:

- `~/.local/llm-ops/bin`

Default public launcher path:

- `~/.local/bin/llmops`

What gets installed:

- `scripts/` -> `~/.local/llm-ops/current/scripts/`
- `bin/` -> `~/.local/llm-ops/current/bin/`

What gets linked:

- managed commands in `~/.local/llm-ops/bin`, based on `scripts/runtime-links.manifest`
- those links point at the installed runtime under `~/.local/llm-ops/current`, not back to the git checkout
- `~/.local/bin/llmops` points at the installed dispatcher and is the only generic PATH entry installed by default

This is useful when you do not want runtime commands to break if `~/projects/LLM-Ops-Kit` is moved or deleted.

Upgrade behavior:

- the new payload and manifest are prepared before `current` is replaced
- the previous payload is backed up under `~/.local/state/llm-ops/backups`
- failed link deployment restores the previous payload and state file
- runtime state is written atomically after link verification

Deployment note:

- administrator workstation deployment uses `scripts/llmops-admin`
- remote apply installs or refreshes the runtime payload and command links on target hosts
- `install-runtime.sh` remains useful for local repair workflows
- `--venv-path` optionally creates or reuses a dedicated runtime Python virtualenv
- the installer records that venv path in the runtime state file so toolkit wrappers can prepend it to `PATH`
- `--install-secrets-kit` optionally installs `Secrets-Kit` into that same runtime venv
