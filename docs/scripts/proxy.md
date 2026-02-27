# proxy

**Created**: 2026-02-26
**Updated**: 2026-02-27

## Purpose
Manage proxy tap lifecycle for request/response visibility.

## Design
- Thin launcher only.
- No persisted config state.
- Wrapper does not inject operational defaults.
- Defaults come from `bin/openai-proxy-tap` / `scripts/openai_proxy_tap.py`.
- `start`/`restart` pass options through directly to `openai-proxy-tap` with no wrapper-level validation.

## Syntax
```bash
~/bin/proxy [start|stop|restart|status] [--listen-host <host>] [--port <port>|--listen-port <port>] --upstream <host:port|url> [--chat-template <path>] [--no-chat-template] [--raw-response-log <path>] [--force]
```

## Examples
```bash
~/bin/proxy restart --upstream 10.0.0.67:11434
~/bin/proxy restart --port 18081 --upstream 10.0.0.67:11434
~/bin/proxy restart --upstream 10.0.0.67:11434 --chat-template ~/projects/agent-work/scripts/templates/Qwen3.5-chatml-tools.jinja
~/bin/proxy restart --upstream 10.0.0.67:11434 --raw-response-log ~/.openclaw/logs/openai-proxy.responses.log
```

## Notes
- Use `status` to check process state (`running/stopped/stale`).
- For full runtime args, inspect process list (`ps`) and logs.
- `--upstream` is required.
- If `--port`/`--listen-port` is omitted, proxy listens on the same port as upstream.
- Default bind is `127.0.0.1` unless you pass `--listen-host`.
- `status` now reports parsed live runtime details from the running proxy process.
