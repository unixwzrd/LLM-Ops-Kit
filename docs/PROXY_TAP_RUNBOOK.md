# OpenAI Proxy Tap Runbook

## Purpose

Capture exactly what OpenClaw sends to the model API, with low-latency log writes and optional image-history guardrails.

## Start proxy (default)

```bash
openai-proxy-tap
```

Defaults from wrapper (`~/bin/openai-proxy-tap`):

- `UPSTREAM=http://10.0.0.67:11434`
- `LISTEN_HOST=127.0.0.1`
- `LISTEN_PORT=18080`
- `LOG_PATH=~/.openclaw/logs/openai-proxy.ndjson`
- `LATEST_IMAGE_ONLY=1`
- `LOG_FSYNC=0`

## Start proxy with Jinja-rendered prompt logging

```bash
openai-proxy-tap --chat-template /Volumes/mps/bin/chatml-tools.jinja
```

This adds `rendered_prompt` (and `rendered_prompt_error`) to `request_start` events.

## Strict flush mode (durability over speed)

```bash
LOG_FSYNC=1 openai-proxy-tap
```

## Verify live traffic (immediate request-start + request-end)

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson \
| jq --unbuffered -r '
    fromjson? \
    | select(.) \
    | select(.path=="/v1/chat/completions") \
    | [.ts, .event, (.response_status // "-"), (.duration_ms // "-")] \
    | @tsv'
```

## Role-structured view (readable request outline)

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson \
| jq --unbuffered -r '
    fromjson? \
    | select(.) \
    | select(.event=="request_start" and .path=="/v1/chat/completions") \
    | .request_summary as $s \
    | [
        .ts,
        ("roles=" + (($s.role_counts // {})|tojson)),
        ("tools=" + (($s.tool_call_counts // {})|tojson)),
        ("last_user=" + (($s.last_user_preview // "")|gsub("\\s+";" ")))
      ] \
    | @tsv'
```

## View final prompt text after Jinja rendering

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson \
| jq --unbuffered -r '
  fromjson?
  | select(.)
  | select(.event=="request_start" and .path=="/v1/chat/completions")
  | [
      .ts,
      "=== RENDERED PROMPT ===",
      (.rendered_prompt // ""),
      "=== TEMPLATE ERROR ===",
      (.rendered_prompt_error // ""),
      ""
    ]
  | join("\n")'
```

## Full pretty request/response blocks

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson \
  | jq --unbuffered -Rr '
      fromjson?
      | select(.)
      | [.ts, (.event // ""), .path, "=== REQUEST ===", (.request_text // ""), "=== RESPONSE ===", (.response_text // ""), ""]
      | join("\n")
    ' \
  | tee -a ~/.openclaw/logs/openai-proxy.pretty.log
```

## Notes

- If stale-image loops appear, keep `LATEST_IMAGE_ONLY=1`.
- If gateway is down, proxy may still run but no new requests will appear.
- For OpenClaw config, point llama.cpp provider to:
  - `http://127.0.0.1:18080/v1`
