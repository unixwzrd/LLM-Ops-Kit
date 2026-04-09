# agentctl

`agentctl` is the supported operator-facing command for agent runtime control.

Use it when you want a control surface that matches `modelctl` and keeps agent operations separate from model operations.

## Usage

```bash
~/bin/agentctl [start|stop|restart|status|logs|setup] [openclaw|hermes|all]
~/bin/agentctl exec [openclaw|hermes] <command> [args...]
~/bin/agentctl [launchd-install|launchd-start|launchd-stop|launchd-enable|launchd-disable|launchd-remove|launchd-status] [openclaw|hermes|all]
```

## Notes

- `agentctl` is the toolkit-owned implementation for OpenClaw and Hermes runtime control.
- Per-agent overrides live under `~/.llm-ops/config/agents/`.
- Launchd uses the internal `agentctl launchd-run <backend>` path so backend-native `.env` files and selective `seckit` exports can be loaded without workspace-local wrappers.
- Agents may also source a small shell init file before their native `.env`; Hermes defaults this to `~/.bashrc` so Conda/Python initialization can be picked up in managed runs.
- `launchd-install` writes a per-backend plist under `~/Library/LaunchAgents/` and starts it immediately.
- `launchd-start` and `launchd-stop` manage the loaded agent without rewriting the plist.
- `launchd-enable` and `launchd-disable` control whether launchd may run the agent automatically.
- `launchd-remove` unloads the service and deletes the plist.
- `exec` runs a backend CLI command under the same managed shell init, backend `.env`, and selective `seckit` export path used by the wrapper. Use this for commands like `agentctl exec openclaw status` or `agentctl exec openclaw update` when the standalone CLI would otherwise miss secrets.
- Hermes gateway arguments can be customized in `~/.llm-ops/config/agents/hermes.env` with `HERMES_GATEWAY_ARGS`. The default is `--replace` so managed restarts clean up stale Hermes PID/session state.
