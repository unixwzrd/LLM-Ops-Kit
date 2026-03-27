# gateway

**Created**: 2026-02-26
**Updated**: 2026-03-26

## Purpose

Manage one or more messaging gateways through a single LLM-Ops-Kit wrapper.

The wrapper supports these backends:

- `openclaw` — launches `openclaw gateway run --port ...` in direct-run mode
- `hermes` — launches `hermes gateway run` in direct-run mode
- `all` — manages both wrappers side by side

OpenClaw remains the default target unless `LLMOPS_GATEWAY_BACKEND` is set or an explicit target is passed on the command line.

## Syntax

```bash
~/bin/gateway [start|stop|restart|status|logs|setup] [openclaw|hermes|all]
```

## Examples

```bash
~/bin/gateway start openclaw
~/bin/gateway start hermes
~/bin/gateway status all
~/bin/gateway logs hermes
```

Hermes setup:

```bash
~/bin/gateway setup hermes
```

## Configuration

Global wrapper precedence:

1. CLI action and optional target argument
2. Exported environment variables
3. `~/.llm-ops/config.env`
4. Wrapper defaults

Important variables:

- `LLMOPS_GATEWAY_BACKEND` — default target when none is passed (`openclaw`, `hermes`, or `all`)
- `LLMOPS_GATEWAY_PORT` — OpenClaw-only direct-run port
- `HERMES_GATEWAY_CMD` — Hermes command to execute when `target=hermes` or `all` (default: `hermes`)

Backend-specific notes:

- OpenClaw runtime settings continue to come from the toolkit env/config layer.
- Hermes runtime settings are owned by Hermes itself under:
  - `~/.hermes/config.yaml`
  - `~/.hermes/.env`
  - legacy `~/.hermes/gateway.json`

## Logs and PIDs

Each backend gets its own toolkit-managed wrapper files:

- OpenClaw:
  - `~/.llm-ops/logs/gateway-openclaw.log`
  - `~/.llm-ops/logs/gateway-openclaw.err.log`
  - `~/.llm-ops/run/gateway-openclaw.pid`
- Hermes:
  - `~/.llm-ops/logs/gateway-hermes.log`
  - `~/.llm-ops/logs/gateway-hermes.err.log`
  - `~/.llm-ops/run/gateway-hermes.pid`

Backend-native logs/status:

- OpenClaw app log: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
- Hermes native log: `~/.hermes/logs/gateway.log`
- Hermes runtime state: `~/.hermes/gateway_state.json`

## Notes

- `gateway setup` is Hermes-only. `gateway setup all` maps to Hermes setup.
- `gateway status all` prints both backend sections.
- `gateway logs all` tails both wrapper logs and backend-native logs where applicable.
