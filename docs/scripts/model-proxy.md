# model-proxy

**Created**: 2026-02-26
**Updated**: 2026-03-27

## Purpose

Manage OpenAI proxy tap lifecycle for request/response visibility.

## Design

- `start` and `restart` pass options through to `model-proxy-tap`.
- Wrapper persists live runtime metadata under `~/.llm-ops/run/model-proxy-live-*` for readable `status` output.
- Wrapper can kill stale listeners on the target listen port during `stop` and `restart`.
- Wrapper checks startup health and fails fast if proxy exits immediately.
- Wrapper resolves `model-proxy-tap` from the active runtime root unless overridden via CLI.

## Syntax

```bash
~/bin/model-proxy [start|stop|restart|status|render] [options...]
~/bin/model-proxy [--start|--stop|--restart|--status] [options...]
```

## Examples

```bash
~/bin/model-proxy restart --upstream http://<upstream-host>:<upstream-port>
~/bin/model-proxy restart --port <listen-port> --upstream http://<upstream-host>:<upstream-port>
~/bin/model-proxy restart --upstream http://<upstream-host>:<upstream-port> --chat-template ~/projects/LLM-Ops-Kit/scripts/templates/Qwen3.5-chatml-tools.jinja
~/bin/model-proxy restart --upstream http://<upstream-host>:<upstream-port> --raw-log ~/.llm-ops/logs/model-proxy.raw.log
~/bin/model-proxy restart --upstream http://<upstream-host>:<upstream-port> --raw-request-log ~/.llm-ops/logs/model-proxy.requests.log --raw-response-log ~/.llm-ops/logs/model-proxy.responses.log
~/bin/model-proxy restart --upstream http://<upstream-host>:<upstream-port> --log-rotate-seconds 86400 --log-rotate-keep 7
~/bin/model-proxy render -i /tmp/payload.json
cat /tmp/payload.json | ~/bin/model-proxy render -i -
```

## Notes

- Config source order for `model-proxy` is:
  1. CLI flags passed to `model-proxy` / `model-proxy-tap`
  2. exported environment variables
  3. `~/.llm-ops/config.env`
  4. built-in wrapper defaults
- Use `status` to check process state (`running`, `stopped`, `stale`).
- `status` reads persisted live settings from `~/.llm-ops/run/model-proxy-live-*`, reports the effective `listen` URL and `upstream`, shows the live listener PID when available, and probes health via `/v1/models`.
- `model-proxy` does not use a dedicated standalone config file; it is driven by env and CLI flags.
- `--upstream` is required unless `LLMOPS_UPSTREAM_HOST` and `LLMOPS_UPSTREAM_PORT` are set in `~/.llm-ops/config.env`.
- If `--port` or `--listen-port` is omitted, proxy listens on the same port as upstream.
- Default bind host is `127.0.0.1` unless `--listen-host` is passed.
- `stop --force` uses SIGKILL for the pid-file process.
- `render` is a non-daemon debugging mode:
  - accepts `-i`, `--input`, or `--render-input`
  - reads one JSON payload or a list of payloads from a file
  - accepts `-` to read JSON from stdin
  - does not bind a port or forward upstream
  - writes the same raw/rendered-style logs used by the live proxy path
- Default framed raw logging is combined into `~/.llm-ops/logs/model-proxy.raw.log` unless explicitly split.
- Proxy-owned logs rotate in place by time using numbered suffixes:
  - active file stays at the configured path
  - previous files become `.0.log`, `.1.log`, and so on
- `--log-rotate-seconds` defaults to `86400` seconds (24 hours).
- `--log-rotate-keep` defaults to `5`.
- `request_end` NDJSON records now include a compact `response_stats` block when upstream returns structured usage/timing data.
  - `usage`: `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_prompt_tokens`
  - `timings`: `prompt_n`, `predicted_n`, `cache_n`, `prompt_ms`, `predicted_ms`, `prompt_per_second`, `predicted_per_second`
  - `finish_reasons`: list of finish reasons from `choices[*].finish_reason`
- Chat-template rendering normalizes assistant tool-call payloads for the renderer:
  - when `tool_calls[*].function.arguments` arrives as a JSON string on the wire, `model-proxy` parses it into a mapping for template rendering only
  - raw request logs remain untouched
  - this keeps stock/original model templates usable during render/debug replay
- Remote-model topology can reuse the same port number locally because the upstream host is different.
- Fully local topology must use a different local listen port than the underlying local model server.
