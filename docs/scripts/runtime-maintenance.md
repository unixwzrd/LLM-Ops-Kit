# runtime-maintenance

**Created**: 2026-03-08
**Updated**: 2026-05-11

Inspect and maintain toolkit-owned runtime artifacts under `~/.local/state/llm-ops`.

```bash
llmops runtime-maintenance [status|rotate|prune|run]
```

Actions:

- `status`
  - Print runtime mode, runtime root, log directory path and size, backup directory path and size, and effective retention settings.
- `rotate`
  - Rotate known active toolkit logs if they exceed `LLMOPS_LOG_ROTATE_BYTES`.
- `prune`
  - Prune rotated logs and runtime install backups according to the configured retention policy.
- `run`
  - Run rotation and pruning in one pass.

Known log targets:

- `~/.local/state/llm-ops/logs/model-proxy-tap.log`
- `~/.local/state/llm-ops/logs/model-proxy-tap.err.log`
- `~/.local/state/llm-ops/logs/tts-bridge.log`
- `~/.local/state/llm-ops/logs/llama-server-*.log`
- `~/.local/state/llm-ops/logs/tts-server-*.log`

Retention controls:

- `LLMOPS_LOG_ROTATE_BYTES`
- `LLMOPS_LOG_ROTATE_KEEP`
- `LLMOPS_LOG_ROTATE_MAX_AGE_DAYS`
- `LLMOPS_BACKUP_KEEP`
- `LLMOPS_BACKUP_MAX_AGE_DAYS`

Examples:

```bash
llmops runtime-maintenance status
llmops runtime-maintenance rotate
llmops runtime-maintenance prune
llmops runtime-maintenance run
```

Notes:

- This command manages toolkit-owned state under `~/.local/state/llm-ops`. It does not rotate OpenClaw-owned logs under `~/.openclaw`, including gateway stdout/stderr capture.
- Active log file paths remain stable. Rotation renames the previous file and recreates the active path in place.
- Install backups are pruned from `~/.local/state/llm-ops/backups`.
