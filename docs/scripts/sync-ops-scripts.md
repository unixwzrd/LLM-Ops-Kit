# sync-ops-scripts

**Created**: 2026-02-28
**Updated**: 2026-02-28

Sync OpenClaw-Ops-Toolkit to a remote host over SSH, refresh runtime link manifest, then deploy and verify runtime links on the remote host in one run.

```bash
~/bin/sync-ops-scripts [--delete] [--dry-run] [--no-links]
```

Examples:

```bash
~/bin/sync-ops-scripts --delete
~/bin/sync-ops-scripts --dry-run
~/bin/sync-ops-scripts --delete --no-links
```

Notes:

- Default behavior includes remote:
  - `deploy-runtime-links.sh`
  - `verify-runtime-links.sh`
- `verify-runtime-links.sh` now checks manifest links plus any dead symlink in `~/bin`.
- If deploy fails, verify is not run (the sync command exits on first failure).
- Use `--no-links` to sync only.
- Uses SSH connection reuse to reduce repeated authentication prompts.
- Use `--help` for all host/user/path/key override options.
