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

## Strict flush mode (durability over speed)

```bash
LOG_FSYNC=1 openai-proxy-tap
```

## Verify live traffic

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson \
| jq -r 'select(.path=="/v1/chat/completions") | [.ts,.response_status, (.request_rewrite.latest_image_only // false), (.error // "")] | @tsv'
```

## Human-readable prompt preview

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson \
| jq --unbuffered -r '
  (try (.request_text | fromjson) catch null) as $r
  | select($r != null and .path=="/v1/chat/completions")
  | .ts as $ts
  | ($r.messages | map(select(.role=="user")) | last) as $u
  | ($u.content
      | if type=="string" then .
        elif type=="array" then (map(select(.type=="text") | .text) | join(" "))
        else "" end) as $txt
  | [$ts, (.request_text|length|tostring), ($txt|gsub("\\s+";" ")|.[0:160])]
  | @tsv'
```

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson \
  | jq --unbuffered -r \
    '[.ts, .path, "=== REQUEST ===", (.request_text // ""), "=== RESPONSE ===", (.response_text // ""), ""]' \
  | join("\n") \
  | tee -a ~/.openclaw/logs/openai-proxy.pretty.log
```

## Notes

- If stale-image loops appear, keep `LATEST_IMAGE_ONLY=1`.
- If gateway is down, proxy may still run but no new requests will appear.
- For OpenClaw config, point llama.cpp provider to:
  - `http://127.0.0.1:18080/v1`
