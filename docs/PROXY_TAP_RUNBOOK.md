# OpenAI Proxy Tap Runbook

**Created**: 2026-02-22
**Updated**: 2026-02-26

- [OpenAI Proxy Tap Runbook](#openai-proxy-tap-runbook)
  - [Purpose](#purpose)
  - [Start Proxy (Default)](#start-proxy-default)
  - [Start Proxy With Rendered Prompt Logging](#start-proxy-with-rendered-prompt-logging)
  - [Strict Flush Mode](#strict-flush-mode)
  - [Direct Logs (No jq)](#direct-logs-no-jq)
  - [jq Parse Pattern (Important)](#jq-parse-pattern-important)
  - [Live Traffic View](#live-traffic-view)
  - [Role / Tool Summary View](#role--tool-summary-view)
  - [Rendered Prompt (Human Readable)](#rendered-prompt-human-readable)
  - [Rendered Prompt (Only Body)](#rendered-prompt-only-body)
  - [Extract Latest Rendered Prompt To File](#extract-latest-rendered-prompt-to-file)
  - [Framed Raw Request Stream](#framed-raw-request-stream)
  - [Full Pretty Request/Response Blocks](#full-pretty-requestresponse-blocks)
  - [Troubleshooting](#troubleshooting)
  - [Clean Restart + 3-Request Validation](#clean-restart--3-request-validation)

## Purpose

Capture what OpenClaw sends to the model with enough observability to debug prompt shaping, tool-call flow, retries, and timeouts.

## Start Proxy (Default)

```bash
~/bin/openai-proxy-tap
```

Default wrapper values (`~/bin/openai-proxy-tap`):

- `UPSTREAM=http://10.0.0.67:11434`
- `LISTEN_HOST=127.0.0.1`
- `LISTEN_PORT=18080`
- `LOG_PATH=~/.openclaw/logs/openai-proxy.ndjson`
- `RAW_REQUEST_LOG=~/.openclaw/logs/openai-proxy.requests.log`
- `RENDERED_PROMPT_LOG=~/.openclaw/logs/openai-proxy.rendered.log`
- `LATEST_IMAGE_ONLY=1`
- `LOG_FSYNC=0`

Sample output:

```text
[openai-proxy-tap] listening on 127.0.0.1:18080 -> http://10.0.0.67:11434
```

## Start Proxy With Rendered Prompt Logging

```bash
~/bin/openai-proxy-tap --chat-template ~/projects/agent-work/scripts/templates/chatml-tools.jinja
```

Sample output:

```text
[openai-proxy-tap] chat template loaded: /Users/miafour/projects/agent-work/scripts/templates/chatml-tools.jinja
```

## Strict Flush Mode

```bash
LOG_FSYNC=1 ~/bin/openai-proxy-tap
```

Sample output:

```text
[openai-proxy-tap] fsync enabled
```

## Direct Logs (No jq)

```bash
tail -F ~/.openclaw/logs/openai-proxy.requests.log
```

Sample output:

```text
=== REQUEST START 2026-02-23T23:57:36.210Z ===
{"model":"Qwen3...","messages":[...],"tools":[...]}
=== REQUEST END ===
```

```bash
tail -F ~/.openclaw/logs/openai-proxy.rendered.log
```

Sample output:

```text
=== RENDERED PROMPT START 2026-02-23T23:57:36.210Z ===
<|im_start|>system
...
<|im_start|>assistant
=== RENDERED PROMPT END ===
```

## jq Parse Pattern (Important)

Use this pattern so commands work whether lines are plain JSON objects or JSON strings:

```jq
(fromjson? // .)
```

## Live Traffic View

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson | jq --unbuffered -r '
  (fromjson? // .)
  | select(.path=="/v1/chat/completions")
  | [.ts, .event, (.response_status // "-"), (.duration_ms // "-")]
  | @tsv'
```

Sample output:

```text
2026-02-23T23:57:36.210342+00:00	request_start	-	-
2026-02-23T23:57:37.910112+00:00	request_end	200	1699
```

## Role / Tool Summary View

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson | jq --unbuffered -r '
  (fromjson? // .)
  | select(.event=="request_start" and .path=="/v1/chat/completions")
  | .request_summary as $s
  | [
      .ts,
      ("roles=" + (($s.role_counts // {})|tojson)),
      ("tools=" + (($s.tool_call_counts // {})|tojson)),
      ("last_user=" + (($s.last_user_preview // "")|gsub("\\s+";" ")))
    ]
  | @tsv'
```

Sample output:

```text
2026-02-23T23:57:36.210342+00:00	roles={"developer":1,"user":1}	tools={}	last_user=Please use web_search with query only...
```

## Rendered Prompt (Human Readable)

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson | jq --unbuffered -r '
  (fromjson? // .)
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

Sample output:

```text
2026-02-23T23:57:36.210342+00:00
=== RENDERED PROMPT ===
<|im_start|>system
...
<|im_start|>assistant
=== TEMPLATE ERROR ===
```

## Rendered Prompt (Only Body)

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson | jq --unbuffered -r '
  (fromjson? // .)
  | select(.event=="request_start" and .path=="/v1/chat/completions")
  | .rendered_prompt'
```

Sample output:

```text
<|im_start|>system
Make tool calls when needed.
...
<|im_start|>assistant
```

## Extract Latest Rendered Prompt To File

```bash
jq -s -r '
  map(if type=="string" then (fromjson? // empty) else . end)
  | map(select(.event=="request_start" and .path=="/v1/chat/completions"))
  | last
  | .rendered_prompt // ""
' ~/.openclaw/logs/openai-proxy.ndjson > /tmp/last-rendered-prompt.txt
```

Sample output:

```text
# command writes file only
# inspect with:
wc -l /tmp/last-rendered-prompt.txt
# 214 /tmp/last-rendered-prompt.txt
```

## Framed Raw Request Stream

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson | jq --unbuffered -r '
  (fromjson? // .)
  | select(.event=="request_start" and .path=="/v1/chat/completions")
  | [
      .ts,
      "================ REQUEST START ================",
      (.request_text // ""),
      "================= REQUEST END =================",
      ""
    ]
  | join("\n")'
```

Sample output:

```text
2026-02-23T23:57:36.210342+00:00
================ REQUEST START ================
{"model":"...","messages":[...],"tools":[...]}
================= REQUEST END =================
```

## Full Pretty Request/Response Blocks

```bash
tail -F ~/.openclaw/logs/openai-proxy.ndjson | jq --unbuffered -r '
  (fromjson? // .)
  | [.ts, (.event // ""), .path, "=== REQUEST ===", (.request_text // ""), "=== RESPONSE ===", (.response_text // ""), ""]
  | join("\n")'
```

Sample output:

```text
2026-02-23T23:57:36.210342+00:00
request_start
/v1/chat/completions
=== REQUEST ===
{"model":"..."}
=== RESPONSE ===

```

## Troubleshooting

- If you see `jq: ... INVALID_CHARACTER`, remove trailing spaces after `\` or use single-line commands.
- If no output appears, verify proxy is active and OpenClaw `baseUrl` points to `http://127.0.0.1:18080/v1`.
- If you get only `request_start` and no `request_end`, request is still in-flight or hung upstream.
- `openai-proxy.rendered.log` is populated only when proxy runs with `--chat-template`.
- If outputs look duplicated, confirm you do not have multiple `tail -F ... | jq ...` pipelines running.

## Clean Restart + 3-Request Validation

After truncating logs and restarting services:

1. Web request (tool-heavy)
2. Plain chat request
3. Memory recall request

For each request, verify:

- `request_start` appears
- matching `request_end` appears
- role/tool counts are sane
- no repeated `CRITICAL` loop events
