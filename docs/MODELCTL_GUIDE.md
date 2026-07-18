# Model Profiles

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

Models are canonical JSON documents under `~/.config/llm-ops/models/`. `modelctl` is an internal typed driver used by component operations.

```json
{
  "schema_version": 1,
  "name": "chat",
  "type": "llm",
  "model_path": "/models/chat.gguf",
  "runtime": {
    "host": "127.0.0.1",
    "port": 11434,
    "threads": "auto",
    "threads_batch": "auto"
  },
  "llama": {
    "ctx_size": 32768,
    "gpu_layers": "auto",
    "batch_size": 1024,
    "ubatch_size": 512,
    "use_mlock": true,
    "use_no_mmap": true,
    "direct_io": true
  },
  "template": {
    "enabled": false,
    "path": null
  },
  "server": {
    "cache_prompt": true,
    "extra_flags": []
  }
}
```

Embedding and TTS profiles use `type: embedding` or `type: tts`. Temporary emergency overrides may be exported into the process environment. Persisted behavior belongs in JSON.

`Qwen-3_5-stock-template.jinja` is retained as the unchanged upstream baseline. `Qwen-3_5-latest-image-template.jinja` is derived from that baseline and keeps only the final image, audio, and video payload of each type. Earlier media-producing tool calls and responses are omitted as complete message pairs, as are later tool calls that duplicate embedded media bytes. The model profile and model-proxy diagnostic renderer should reference the same selected template so rendered logs match the prompt produced by llama.cpp.

```bash
llmops component plan restart <stack>:<model-component>
llmops component restart <stack>:<model-component>
llmops component status <stack>:<model-component>
```

There are no launcher-name profiles, repository shell profiles, model registry mutation, or implicit agent switching.

Each model start archives a nonempty prior server log before opening a new one. Lifecycle events are appended to `~/.local/state/llm-ops/logs/model-lifecycle.log`. If a managed process exits unexpectedly, the next status inspection records `unexpected_exit_detected` before clearing stale PID state. Automatic restart remains an explicit future policy rather than a default because model memory and startup cost vary substantially.
