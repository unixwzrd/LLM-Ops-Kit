# Textual Console

**Created**: 2026-07-20
**Updated**: 2026-07-20

Back: [Documentation index](./INDEX.md)

Run the on-demand console with:

```bash
llmops tui
```

The normal installation includes Textual. A `--minimal` installation intentionally omits it. The console runs in the foreground, starts no daemon, and remains independent of every managed model and agent.

## Controls

| Key | Action |
|---|---|
| `r` | Refresh component status |
| `s` | Start the selected component and missing dependencies |
| `x` | Stop the selected component subject to dependency protection |
| `b` | Restart only the selected component |
| `l` | Show recent component logs |
| `e` | Edit supported fields on the selected component |
| `v` | Toggle component and stack views |
| `u` | Check for a toolkit update |
| `Ctrl+U` | Review and apply a toolkit update |
| `d` | Run deterministic configuration validation |
| `q` | Exit |

Every lifecycle or configuration mutation displays its dependency plan and equivalent `llmops` command before confirmation. Configuration updates write a backup, validate the complete topology, and restore the backup on failure.

The beta editor covers existing component host, profile, ownership, enabled state, dependencies, and readiness timeout. Advanced or adapter-specific fields remain canonical JSON until their schemas stabilize.

The console never accepts secret values and does not perform autonomous remediation. Adapter-specific forms, host creation, corrective suggestions from active probes, and a correlated model-proxy exchange browser remain post-beta work; raw component logs are available now.
