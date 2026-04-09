# How It Works

Back: [docs/INDEX.md](./INDEX.md)

This is a plain-language overview of the moving parts and how they fit together.

## The Big Picture

`LLM-Ops-Kit` is the operations layer around an agent runtime (OpenClaw or Hermes).
It owns the run commands, profiles, and the glue between models, tools, and services.

## Main Components

- **agentctl**: starts and stops agent runtimes (OpenClaw or Hermes).
- **modelctl**: starts and stops model servers (LLM, embeddings, TTS).
- **model-proxy / model-proxy-tap**: optional request routing and observability for model calls.
- **tts-bridge**: OpenAI-compatible wrapper that forwards to MLX Audio for voice output.

## Typical Flow (Local Model)

1. `modelctl` starts the LLM server (llama.cpp).
2. `agentctl` starts OpenClaw or Hermes.
3. The agent runtime sends prompts to the model server.
4. Optional proxy and tap layers log or transform requests.
5. Optional TTS bridge converts responses into audio for channels like Telegram.

## Hermes vs OpenClaw

- **OpenClaw** is the main agent runtime with plugins, tools, and memory.
- **Hermes** is a separate runtime with its own config and platform adapters.
- `agentctl switch` lets you stop one and start the other quickly.

## Multi-host and Cloud Topology (Future)

The current workflow assumes a single model host, but it is designed so:

- Model servers can run on a different host than the agent runtime.
- `model-proxy` can forward to remote model hosts.
- `tts-bridge` can forward to a remote MLX Audio server.

We will document multi-host presets once the switching UX is stable.

## See Also

- [Switching Models and Agents](./SWITCHING.md)
- [Quickstart](./QUICKSTART.md)
- [Configuration](./CONFIGURATION.md)
- [Architecture](./ARCHITECTURE.md)
