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

## Typical Flow

1. `modelctl` starts the LLM server (llama.cpp).
2. `modelctl` starts embeddings and optional MLX Audio TTS.
3. `model-proxy` and `tts-bridge` connect agent-local ports to model services.
4. `agentctl` starts OpenClaw or Hermes after its dependencies are healthy.
5. Optional Headroom evaluates or reduces context on a deliberately configured
   route; it is not automatically inserted by LLM-Ops-Kit.
6. A dashboard or Desktop client connects after the agent is ready.

## Hermes vs OpenClaw

- **OpenClaw** is the main agent runtime with plugins, tools, and memory.
- **Hermes** is a separate runtime with its own config and platform adapters.
- `agentctl switch` lets you stop one and start the other quickly.

## Multi-host Topology

- Model servers can run on a different host than the agent runtime.
- `model-proxy` can forward to remote model hosts.
- `tts-bridge` can forward to a remote MLX Audio server.
- Inventory-based staging deploys the same immutable runtime to both hosts.
- Host-specific JSON profiles keep absolute interpreters, ports, and upstreams
  out of the portable repo defaults.

Launchd and non-interactive SSH do not activate Conda. Managed services should
therefore use absolute interpreter paths and explicit runtime PATH additions.

## See Also

- [Switching Models and Agents](./SWITCHING.md)
- [Quickstart](./QUICKSTART.md)
- [Configuration](./CONFIGURATION.md)
- [Architecture](./ARCHITECTURE.md)
