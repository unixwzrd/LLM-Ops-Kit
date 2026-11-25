# Optional Hermes HTTPX Capture Binding

**Created**: 2026-11-24
**Updated**: 2026-11-24

This operator integration preserves Hermes' canonical provider URLs and credentials. It wraps HTTPX 0.28.1's standard sync/async transport methods after SDK authentication and request hooks, diverting only configured HTTPS provider origin/path prefixes to fixed loopback tap routes. It reuses the original body stream/headers, leaves auth-refresh endpoints and unrelated traffic alone, and adds no fallback or retry layer.

The tap remains client-independent; this optional binding needs an existing HTTPX 0.28.1 in the agent runtime. It installs no dependencies or Hermes core changes. Incompatible versions refuse selected-process startup explicitly. Requalify after runtime updates. This is not a vendor-supported Hermes plugin and does not cover WebSockets/custom/non-HTTPX transports.

Stage [sitecustomize.py](sitecustomize.py) in an owner-private bootstrap directory with an owner-private map:

```json
{
  "https://chatgpt.com/backend-api/codex": "http://127.0.0.1:18081/codex",
  "https://api.openai.com/v1": "http://127.0.0.1:18081/openai/v1",
  "https://openrouter.ai/api/v1": "http://127.0.0.1:18081/openrouter/v1"
}
```

Set the selected service's `PYTHONPATH` to that bootstrap directory and the installed toolkit's `scripts/`, preserving previous entries. Set `MODEL_PROXY_TRANSPORT_MAP` to the map. For example:

```text
PYTHONPATH=/private/agent-proxy/bootstrap:/path/to/llm-ops-release/scripts
MODEL_PROXY_TRANSPORT_MAP=/private/agent-proxy/bootstrap/routes.json
```

Only `python -m hermes_cli.main` and its stderr supervisor are instrumented; arbitrary inherited Python subprocesses are excluded. No credentials belong in these files. The bootstrap appends a private PID/qualification receipt beside the map.

Back up exact launch definitions and manifests that pin their hashes. Check workloads before an agent restart, qualify offline, bind only intended service environments, and reconcile manifests explicitly. Make the external tap supervised and declare its consumer dependencies. Verify the actual agent surface, native identity/account headers and compression, request/response, and read-only status. Preserve existing restricted-controller/SSH bindings when distributing topology. No SSH grants are supplied here.

See the [proxy runbook](../../PROXY_TAP_RUNBOOK.md) for capture, privacy and reload boundaries.
