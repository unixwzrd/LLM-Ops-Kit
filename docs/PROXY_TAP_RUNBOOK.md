# Model Proxy: See What Your Agent Is Whispering to the Model

**Created**: 2026-07-15
**Updated**: 2026-11-24

Back: [Documentation index](./INDEX.md)

The proxy observes local models and explicitly routed external HTTP/SSE services, including OpenAI Responses and Chat Completions. It forwards bodies unchanged while producing separate body captures, structured diagnostics, and optional human-readable exchanges. It does not optimize, prune or rewrite the request sent upstream.

## Separate local and external listeners

Give each tap a component, port, private log directory and trusted report file. Register external taps as dependencies of their consuming agent surfaces. A running listener alone does not prove interception; verify an actual request from the intended client.

Configure `runtime.upstream_url` for one fixed HTTP(S) upstream, or `runtime.routes_file` for a prefix-to-upstream JSON map. Both override legacy upstream host/port settings; do not configure a URL and route map together. See the [external service profile](examples/services/model-proxy-external.json) and [provider map](examples/services/model-proxy-routes.json).

```json
{
  "/openai": "https://api.openai.com",
  "/openrouter": "https://openrouter.ai/api",
  "/codex": "https://chatgpt.com/backend-api/codex"
}
```

For a tap on port 18081, API-key clients can use `http://127.0.0.1:18081/openai/v1` or `http://127.0.0.1:18081/openrouter/v1`. Only the configured prefix is removed. Unknown prefixes return 404; upstream redirects are returned rather than followed with credentials; credentials embedded in upstream URLs are refused. This is an operator-controlled reverse proxy, not an open forward proxy.

Native OAuth clients may depend on their canonical URL for identity/account headers, compression, compaction and credential-host rules. Do not blindly substitute a loopback base URL. The [optional Hermes HTTPX binding](examples/hermes-httpx/README.md) retains canonical URLs and diverts only allowlisted physical HTTPX requests. It is qualified for HTTPX 0.28.1, not arbitrary transports.

## Human-readable Jinja reports

Enable `logging.exchange_log` in a model-proxy service profile. The managed wrapper defaults to the bundled `scripts/templates/model-proxy-readable-exchange.jinja`; `template.report_path` selects a separate trusted operator copy. Keep each listener's report independently editable.

The report shows the latest user message as an explicitly repeated overview, the complete numbered input order, named tool calls/results with call IDs, multiline content, supplied instructions, full tool definitions and request settings. Responses lead with assistant text/tool calls and compact provider-reported token usage/attribution.

Reading sections overlap: the overview and extracted instructions are not extra inputs sent upstream. Character counts are not billed tokens. Server-side history references are labelled; hidden earlier context is not reconstructed.

Captured strings are data, never Jinja source. Display filters decode structured tool arguments/results and preserve paragraph breaks while escaping terminal controls. Opaque encrypted items and inline media are labelled instead of dumping unusable base64. This indented reading view is not round-trippable serialization. Full values remain in the separate full-mode body/NDJSON diagnostics. Set `show_detailed_usage = true` in the report for complete provider usage details.

## Logs and privacy

```bash
llmops component logs <component> --list
llmops component logs <component> --channel readable-exchange --follow
llmops component logs <component> --channel raw-request
llmops component logs <component> --channel raw-response
```

- `model-proxy.ndjson`: structured diagnostics, timings, request IDs, bodies, provider usage and redacted credential headers.
- `model-proxy.raw.log`: framed request/response body or SSE diagnostic text.
- Configured `logging.exchange_log`: the derived human-readable view.
- `model-proxy.rendered.log`: optional model-specific chat rendering.

Here “raw” means HTTP-body/SSE diagnostic text, including diagnostic decompression where configured, not a packet capture or complete secret-bearing header dump. Authorization, API-key, proxy-authorization and cookie headers are redacted. Secrets inside prompt bodies/tool results are not automatically redacted: keep directories owner-private, bound retention, and use synthetic public examples.

`logging.mode: metadata` excludes bodies, arbitrary headers/URLs, previews, readable reports, rendered prompts and reasoning from all new proxy records. Timing, status, byte counts and numeric usage remain. Existing files are not scrubbed; agent/server/provider logging is separate. No response cache is added.

For zstd requests, `runtime.decoder_python` can select an existing absolute Python 3.14+ executable. An isolated bounded stdlib decoder operates on a diagnostic copy over pipes; forwarded compressed bytes remain untouched. Unsupported encodings/decoder failures are explicitly labelled. This does not add response decompression.

## Reload templates while requests continue

Send SIGHUP to the verified owner-local Python listener PID, not a shell/osascript supervisor:

```bash
kill -HUP <verified-listener-pid>
```

The next request compiles the chat/report pair atomically. In-flight exchanges retain their original template snapshot. Compilation failures keep the last good pair; formatting failures cannot rewrite traffic. Later template-only edits need no restart; changing Python filter implementations requires an idle proxy restart.

Reload affects diagnostic presentation only, not the model server's serving template or the request body. A lifecycle manifest that pins a chat-template hash may require explicit reconciliation before a later restart.

## Private offline previews, without replay

```bash
python scripts/model_proxy_report_preview.py \
  --ndjson /private/agent-proxy/model-proxy.ndjson \
  --request-id <captured-request-id> \
  --template scripts/templates/model-proxy-readable-exchange.jinja \
  --output /private/new-preview-directory
```

The helper writes request/response previews and a receipt into a new owner-private directory, without importing a provider SDK or making network calls. It also accepts matching original JSON-heavy frames with `--request-frame` and `--response-frame`. Pasted reading frames recover only fields they contained, not hidden headers or wire bytes.

## Qwen 3.8 is a different template

The [optimized Qwen 3.8 template](QWEN_3_8_TEMPLATE.md) omits closed-turn tool calls/results from model-specific rendered history while preserving the active tool chain. Selecting it as the proxy's `template.path` renders diagnostics only; inference changes require the model server's supported template configuration. The external exchange report is separate. Qwen 3.5 compatibility is not asserted for the optimized template; the older file remains for existing configurations.

## Acceptance boundaries

The reserved `GET /_model_proxy/health` endpoint checks listener readiness without any upstream request or prompt log. Its response explicitly says `scope: listener-only` and `provider_health: not-probed`. Managed external-route status uses this endpoint rather than manufacturing unauthenticated provider requests. It is not an authentication or provider-health check.

Verify an actual authenticated routed request with its intended model, route, tools/history and response. An unauthenticated discovery HTTP 401 is expected reachability evidence, not expired OAuth and not authenticated-generation acceptance. Never replay private production traffic simply to test logging.

HTTP/SSE is supported; WebSocket upgrades are not. Non-HTTPX/custom transports, separately launched sessions and other provider origins require separate routing/qualification. Existing correlation headers are retained, but the proxy does not invent complete session/turn instrumentation or claim access to hidden provider prompts. No current capture result establishes protected multi-user authorization.

Request bodies must have at most one nonnegative Content-Length. Chunked/streamed request bodies are explicitly refused instead of being silently forwarded empty; streamed SSE responses are supported.
