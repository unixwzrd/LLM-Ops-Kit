
# OpenAI Proxy Tap Runbook

**Created**: 2026-02-22
**Updated**: 2026-03-01

- [OpenAI Proxy Tap Runbook](#openai-proxy-tap-runbook)
  - [Purpose](#purpose)
  - [Start Proxy (Default)](#start-proxy-default)
  - [Start Proxy With Rendered Prompt Logging](#start-proxy-with-rendered-prompt-logging)
  - [Strict Flush Mode](#strict-flush-mode)
  - [Local Example (Template)](#local-example-template)
  - [Direct Logs (No jq)](#direct-logs-no-jq)
  - [jq Parse Pattern (Important)](#jq-parse-pattern-important)
  - [Live Traffic View](#live-traffic-view)
  - [Role / Tool Summary View](#role--tool-summary-view)
  - [Rendered Prompt (Human Readable)](#rendered-prompt-human-readable)
  - [Rendered Prompt (Only Body)](#rendered-prompt-only-body)
  - [Extract Latest Rendered Prompt To File](#extract-latest-rendered-prompt-to-file)
  - [Framed Raw Request Stream](#framed-raw-request-stream)
  - [Combined Raw File (Recommended)](#combined-raw-file-recommended)
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

- `UPSTREAM=http://<upstream-host>:<upstream-port>`
- `LISTEN_HOST=127.0.0.1`
- `LISTEN_PORT=18080`
- `LOG_PATH=~/.openclaw/logs/openai-proxy.ndjson`
- `RAW_LOG=~/.openclaw/logs/openai-proxy.raw.log` (combined request + response)
- `RENDERED_PROMPT_LOG=~/.openclaw/logs/openai-proxy.rendered.log`
- `LATEST_IMAGE_ONLY=1`
- `LOG_FSYNC=0`

Sample output:

```text
openai-proxy-tap listening on http://127.0.0.1:18080 -> http://<upstream-host>:<upstream-port> ...
```

## Start Proxy With Rendered Prompt Logging

```bash
~/bin/openai-proxy-tap --chat-template ~/projects/LLM-Ops-Kit/scripts/templates/chatml-tools.jinja
```

Note: template-load status is reflected in NDJSON fields (`rendered_prompt` / `rendered_prompt_error`).

## Strict Flush Mode

```bash
LOG_FSYNC=1 ~/bin/openai-proxy-tap
```

No special banner is guaranteed for fsync mode; verify by expected log durability behavior.

## Local Example (Template)

```text
UPSTREAM=http://<upstream-host>:<upstream-port>
LISTEN_HOST=127.0.0.1
LISTEN_PORT=18080
```

## Direct Logs (No jq)

```bash
tail -F ~/.openclaw/logs/openai-proxy.raw.log
```

Sample output:

```text
=== RAW_REQUEST START 2026-02-23T23:57:36.210Z ===
{"model":"Qwen3...","messages":[...],"tools":[...]}
=== RAW_REQUEST END 2026-02-23T23:57:36.210Z ===
```

```bash
tail -F ~/.openclaw/logs/openai-proxy.rendered.log
```

Sample output:

```text
=== RENDERED_PROMPT START 2026-02-23T23:57:36.210Z ===
<|im_start|>system
...
<|im_start|>assistant
=== RENDERED_PROMPT END 2026-02-23T23:57:36.210Z ===
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
  | .ts as $ts
  | if (.rendered_prompt // "") != "" then
      [$ts, "=== RENDERED_PROMPT ===", .rendered_prompt, ""]
    elif (.rendered_prompt_error // "") != "" then
      [$ts, "=== TEMPLATE_ERROR ===", .rendered_prompt_error, ""]
    else
      [$ts, "=== RENDERED_PROMPT ===", "<empty>", ""]
    end
  | join("\n")
'
```

Sample output:

```text
2026-02-23T23:57:36.210342+00:00
=== RENDERED PROMPT ===
<|im_start|>system
...
<|im_start|>assistant
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

## Combined Raw File (Recommended)

```bash
tail -F ~/.openclaw/logs/openai-proxy.raw.log
```

Sample output:

```text
=== RAW_REQUEST START 2026-02-28T01:23:45.000000+00:00 ===
{"model":"...","messages":[...]}
=== RAW_REQUEST END 2026-02-28T01:23:45.000000+00:00 ===

=== RAW_RESPONSE status=200 START 2026-02-28T01:23:45.000000+00:00 ===
data: {...}
=== RAW_RESPONSE status=200 END 2026-02-28T01:23:46.732000+00:00 ===
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
