# model-proxy

**Created**: 2026-02-26
**Updated**: 2026-03-07

## Purpose

Manage OpenAI proxy tap lifecycle for request/response visibility.

## Design

- `start` and `restart` pass options through to `model-proxy-tap`.
- Wrapper persists live runtime metadata under `~/.llm-ops/run/model-proxy-live-*` for readable `status` output.
- Wrapper can kill stale listeners on the target listen port during `stop` and `restart`.
- Wrapper checks startup health and fails fast if proxy exits immediately.
- Defaults come from `bin/model-proxy-tap` and `scripts/model_proxy_tap.py` unless overridden via CLI.

## Syntax

```bash
~/bin/model-proxy [start|stop|restart|status] [options...]
~/bin/model-proxy [--start|--stop|--restart|--status] [options...]
```

## Examples

```bash
~/bin/model-proxy restart --upstream http://<upstream-host>:<upstream-port>
~/bin/model-proxy restart --port <listen-port> --upstream http://<upstream-host>:<upstream-port>
~/bin/model-proxy restart --upstream http://<upstream-host>:<upstream-port> --chat-template ~/projects/LLM-Ops-Kit/scripts/templates/Qwen3.5-chatml-tools.jinja
~/bin/model-proxy restart --upstream http://<upstream-host>:<upstream-port> --raw-log ~/.llm-ops/logs/model-proxy.raw.log
~/bin/model-proxy restart --upstream http://<upstream-host>:<upstream-port> --raw-request-log ~/.llm-ops/logs/model-proxy.requests.log --raw-response-log ~/.llm-ops/logs/model-proxy.responses.log
```

## Notes

- Use `status` to check process state (`running`, `stopped`, `stale`).
- `status` reads persisted live settings from `~/.llm-ops/run/model-proxy-live-*`, reports the effective `listen` URL and `upstream`, shows the live listener PID when available, and probes health via `/v1/models`.
- `--upstream` is required.
- If `--port` or `--listen-port` is omitted, proxy listens on the same port as upstream.
- Default bind host is `127.0.0.1` unless `--listen-host` is passed.
- `stop --force` uses SIGKILL for the pid-file process.
- Default framed raw logging is combined into `~/.llm-ops/logs/model-proxy.raw.log` unless explicitly split.
