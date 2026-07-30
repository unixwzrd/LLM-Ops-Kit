# Model Proxy Runbook

Back: [Documentation index](./INDEX.md)

The model proxy records request and response metadata, token usage, timings, raw framed traffic, and optional rendered prompts while forwarding OpenAI-compatible request bodies unchanged.

## Operate the Component

```bash
llmops component status model-proxy
llmops config effective component model-proxy
llmops component version model-proxy
llmops component start model-proxy
llmops component restart model-proxy
llmops component logs model-proxy --channel service
llmops component logs model-proxy --channel raw-request
llmops component logs model-proxy --channel rendered-prompt
llmops component logs model-proxy --channel raw-response
llmops component stop model-proxy
```

The proxy profile defines listen address, upstream address, Python interpreter, chat template, and log rotation. The typed component driver invokes the installed implementation; no separately installed wrapper is required.

## Render Diagnostics

Render mode is an advanced diagnostic on the host that owns the proxy component:

```bash
~/.local/llm-ops/bin/model-proxy render --input <payload.json>
~/.local/llm-ops/bin/model-proxy render --input <payload.json> --chat-template <template.jinja>
```

Model responses in the rendered diagnostic log label reasoning returned by the
upstream model separately from visible response content and tool calls. To audit
historical assistant reasoning supplied by a client, start the proxy with
`-t`, `--show-reasoning`, or `--show-source-reasoning`. This adds a
diagnostic-only section showing whether each source reasoning block appears in
the selected template output. It does not add reasoning to the rendered prompt,
alter proxy traffic, or change the verbatim raw request and response logs.

This internal driver command writes the same raw and rendered diagnostic artifacts without starting the listener. Use `-` as the input path to read JSON from standard input.

## Traffic Behavior

- The original request body is always forwarded byte-for-byte unchanged.
- A chat template creates derived logging artifacts; it does not rewrite upstream traffic.
- Each completed rendered-log exchange contains one request ID, the exact template output, the reconstructed model response, and an explicit SSE or HTTP response boundary.
- The proxy has no request-rewriting mode. Context optimization belongs in the model's selected chat template.
- Logs may contain prompts and responses and must be protected as operational data.

## Logs

Default state is under `~/.local/state/llm-ops/logs/`. Log commands execute on the component's configured host as its execution user and report that identity; a remote path is never presented as a local file. Use the profile to relocate logs or change rotation limits. `runtime-maintenance` applies toolkit retention settings without deleting model or agent state.

## Media-History Template

`Qwen-3_5-stock-template.jinja` is the unchanged reference. `Qwen-3_5-media-history-template.jinja` is an optional context-cost policy for textual media tool history. It removes image-producing tool call/result pairs and assistant-side byte copies because truncated tool-result images cannot be reconstructed reliably. Native structured multimodal input remains intact and renders the Qwen vision placeholders used to bind separately processed image data. The template does not validate base64 in Jinja.

## Validation

Confirm `llmops doctor --probe` succeeds, restart the component, send one known request through the configured listener, and verify the response, proxy health, token metadata, and raw/rendered artifact timestamps.
