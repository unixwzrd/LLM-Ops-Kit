# agentctl

`agentctl` is the supported operator-facing command for agent runtime control.

Use it when you want a control surface that matches `modelctl` and keeps agent operations separate from model operations.

## Usage

```bash
~/bin/agentctl [start|stop|restart|status|logs|setup] [openclaw|hermes|all]
```

## Notes

- `agentctl` is the toolkit-owned implementation for OpenClaw and Hermes runtime control.
- Per-agent overrides live under `~/.llm-ops/config/agents/`.
- Launchd uses the internal `agentctl launchd-run <backend>` path so backend-native `.env` files and selective `seckit` exports can be loaded without workspace-local wrappers.
