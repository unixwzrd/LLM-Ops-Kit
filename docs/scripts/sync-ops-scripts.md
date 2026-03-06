# sync-ops-scripts

**Created**: 2026-02-28
**Updated**: 2026-03-03

Sync LLM-Ops-Kit to a remote host over SSH, refresh runtime link manifest, then deploy and verify runtime links on the remote host in one run.

```bash
~/bin/sync-ops-scripts [--delete] [--dry-run] [--no-links] [--runtime-mode <repo|installed>] [--install-prefix <path>] [--state-file <path>]
```

Examples:

```bash
~/bin/sync-ops-scripts --delete
~/bin/sync-ops-scripts --dry-run
~/bin/sync-ops-scripts --delete --no-links
~/bin/sync-ops-scripts --delete --runtime-mode installed
~/bin/sync-ops-scripts --delete --runtime-mode installed --install-prefix ~/.openclaw-ops
```

Notes:

- Prints effective `LOCAL_DIR`, `REMOTE_DIR`, `HOST`, and `USER` at runtime.
- Host defaults are loaded from `scripts/config/hosts.env` (and optional `scripts/config/hosts.local.env`) via shared shell env loading.
- Runs a local manifest precheck before rsync and fails if any manifest source is missing.
- Default behavior includes remote:
  - in `repo` mode:
    - `generate-manifest`
    - `deploy-runtime-links.sh`
    - `verify-runtime-links.sh`
  - in `installed` mode:
    - `install-runtime.sh --source <remote_repo> --prefix <install_prefix>`
- If `--runtime-mode` is not provided, sync auto-detects installed mode from:
  - `~/.openclaw-ops/runtime-state.env`
- `verify-runtime-links.sh` now checks manifest links plus any dead symlink in `~/bin`.
- If deploy fails, verify is not run (the sync command exits on first failure).
- During repo rename migration, deploy auto-heals managed symlinks that still target `~/projects/OpenClaw-Ops-Toolkit/...` to `~/projects/LLM-Ops-Kit/...`.
- Use `--no-links` to sync only.
- Uses SSH connection reuse to reduce repeated authentication prompts.
- Use `--help` for all host/user/path/key override options.
