# Model Proxy Runbook

Back: [Documentation index](./INDEX.md)

The model proxy records request and response metadata, token usage, timings, raw framed traffic, and optional rendered prompts while forwarding OpenAI-compatible request bodies unchanged.

## Operate the Component

```bash
llmops component status model-proxy
llmops component start model-proxy
llmops component restart model-proxy
llmops component logs model-proxy
llmops component stop model-proxy
```

The proxy profile defines listen address, upstream address, Python interpreter, chat template, and log rotation. The typed component driver invokes the installed implementation; no separately installed wrapper is required.

## Render Diagnostics

Render mode is an advanced diagnostic on the host that owns the proxy component:

```bash
~/.local/llm-ops/bin/model-proxy render --input <payload.json>
~/.local/llm-ops/bin/model-proxy render --input <payload.json> --chat-template <template.jinja>
```

This internal driver command writes the same raw and rendered diagnostic artifacts without starting the listener. Use `-` as the input path to read JSON from standard input.

## Traffic Behavior

- The original request body is always forwarded byte-for-byte unchanged.
- A chat template creates derived logging artifacts; it does not rewrite upstream traffic.
- The proxy has no request-rewriting mode. Context optimization belongs in the model's selected chat template.
- Logs may contain prompts and responses and must be protected as operational data.

## Logs

Default state is under `~/.local/state/llm-ops/logs/`. Use the profile to relocate logs or change rotation limits. `runtime-maintenance` applies toolkit retention settings without deleting model or agent state.

## Validation

Confirm `llmops doctor --probe` succeeds, restart the component, send one known request through the configured listener, and verify the response, proxy health, token metadata, and raw/rendered artifact timestamps.
