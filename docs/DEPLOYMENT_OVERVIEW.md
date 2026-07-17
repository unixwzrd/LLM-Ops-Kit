# Deployment

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

The administrator checkout is the one-way desired-state authority. Managed hosts do not need source checkouts.

```bash
llmops deploy --config-home ~/.config/llm-ops --source /path/to/LLM-Ops-Kit --bundle-id <release> --dry-run --json
llmops deploy --config-home ~/.config/llm-ops --source /path/to/LLM-Ops-Kit --bundle-id <release>
```

Deployment validates topology, refuses dirty source unless `--allow-dirty` is supplied, builds a checksummed runtime package, builds one role-filtered configuration archive per host, pushes with bounded retry, applies an immutable release, updates `current` and `previous`, and verifies drift.

Set `deployment.source_root` in the administrator `config.json` to avoid repeating `--source`.

Only code, manifest metadata, and canonical JSON snapshots are synchronized. Model weights, logs, databases, agent state, `.env` files, and secret values are excluded.

Select hosts with `--host-name`, `--role`, or `--tag`. Use `--inventory` to select a deliberate alternate inventory.

```bash
llmops drift --stage ~/.local/share/llm-ops/stage/<release> --json
llmops rollback --dry-run --json
llmops rollback
```

Deployment does not restart running components. After changing an engine or profile, canary with `llmops component restart <component>` and broaden to `--cascade` only when required.
