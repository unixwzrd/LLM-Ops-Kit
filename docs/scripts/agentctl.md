# agentctl

`agentctl` is the supported operator-facing command for agent runtime control.

Use it when you want a control surface that matches `modelctl` and keeps agent operations separate from model operations.

## Quick Examples

```bash
llmops agentctl switch openclaw
llmops agentctl switch hermes
llmops agentctl current
llmops agentctl status openclaw
```

## Usage

```bash
llmops agentctl [start|stop|restart|status|current|switch|logs|setup] [openclaw|hermes|all]
llmops agentctl exec [openclaw|hermes] <command> [args...]
llmops agentctl [launchd-install|launchd-start|launchd-stop|launchd-bootout|launchd-enable|launchd-disable|launchd-remove|launchd-status] [openclaw|hermes|all]
```

## Notes

- `agentctl` is the toolkit-owned implementation for OpenClaw and Hermes runtime control.
- `current` prints which backend is active.
- `switch` stops the other backend and starts the requested backend.
- Per-agent overrides live under `~/.config/llm-ops/config/agents/`.
- Launchd uses the internal `agentctl launchd-run <backend>` path so backend-native `.env` files can be loaded without workspace-local wrappers. For OpenClaw, this path wraps the gateway with `seckit run` only when `LLMOPS_USE_SECKIT=1`.
- Agents may also source a small shell init file before their native `.env`; Hermes defaults this to `~/.bashrc` so Conda/Python initialization can be picked up in managed runs.
- Hermes Secrets Kit use is optional and disabled by default. Keep `~/.hermes/.env` placeholder-only when using an external secret store.
- `launchd-install` writes a per-backend plist under `~/Library/LaunchAgents/` and starts it immediately.
- `launchd-start` and `launchd-stop` manage the loaded agent without rewriting the plist.
- `launchd-bootout` exposes the raw launchd bootout action for cases where you want an explicit unload step without removing the plist.
- `launchd-enable` and `launchd-disable` control whether launchd may run the agent automatically.
- `launchd-remove` unloads the service and deletes the plist.
- `exec` runs a backend CLI command under the same managed shell init and backend `.env` path used by the wrapper. Use this for commands like `agentctl exec openclaw status` or `agentctl exec openclaw update` when the standalone CLI would otherwise miss runtime config.
- Hermes gateway arguments can be customized in `~/.config/llm-ops/config/agents/hermes.env` with `HERMES_GATEWAY_ARGS`. The default is `--replace` so managed restarts clean up stale Hermes PID/session state.
