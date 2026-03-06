# proxy

**Created**: 2026-02-26
**Updated**: 2026-03-01

## Purpose

Manage proxy tap lifecycle for request/response visibility.

## Design

- `start`/`restart` pass options through to `openai-proxy-tap`.
- Wrapper persists live runtime metadata under `~/.openclaw/run/proxy-live-*` for human-readable `status`.
- Wrapper can kill stale/orphan listeners on the target listen port during `stop`/`restart`.
- Wrapper checks startup health and fails fast if proxy exits immediately (for example, bind conflicts).
- Defaults still come from `bin/openai-proxy-tap` / `scripts/openai_proxy_tap.py` unless overridden via CLI.

## Syntax

```bash
~/bin/proxy [start|stop|restart|status] [options...]
~/bin/proxy [--start|--stop|--restart|--status] [options...]
```

## Examples

```bash
~/bin/proxy restart --upstream <upstream-host>:<upstream-port>
~/bin/proxy restart --port <listen-port> --upstream <upstream-host>:<upstream-port>
~/bin/proxy restart --upstream <upstream-host>:<upstream-port> --chat-template ~/projects/LLM-Ops-Kit/scripts/templates/Qwen3.5-chatml-tools.jinja
~/bin/proxy restart --upstream <upstream-host>:<upstream-port> --raw-log ~/.openclaw/logs/openai-proxy.raw.log
~/bin/proxy restart --upstream <upstream-host>:<upstream-port> --raw-request-log ~/.openclaw/logs/openai-proxy.requests.log --raw-response-log ~/.openclaw/logs/openai-proxy.responses.log
```

## Notes

- Use `status` to check process state (`running/stopped/stale`).
- `status` reads persisted live settings from `~/.openclaw/run/proxy-live-*` and reports health via `/v1/models`.
- `--upstream` is required.
- If `--port`/`--listen-port` is omitted, proxy listens on the same port as upstream.
- Default bind is `127.0.0.1` unless you pass `--listen-host`.
- `stop --force` uses SIGKILL for the pid-file process.
- Default framed raw logging is combined into `~/.openclaw/logs/openai-proxy.raw.log` unless explicitly split.
