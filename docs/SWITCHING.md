# Switching Models and Agents

Back: [docs/INDEX.md](./INDEX.md)

This guide focuses on simple, copy-paste commands for switching models and agents.

- [Switching Models and Agents](#switching-models-and-agents)
  - [Switch Agent Runtime](#switch-agent-runtime)
  - [Add a Model to OpenClaw](#add-a-model-to-openclaw)
  - [Switch OpenClaw to the New Model](#switch-openclaw-to-the-new-model)
  - [See Also](#see-also)

## Switch Agent Runtime

```bash
~/bin/agentctl switch openclaw
~/bin/agentctl switch hermes
```

Check what is running:

```bash
~/bin/agentctl current
```

## Add a Model to OpenClaw

Add a new model entry using a local GGUF path:

```bash
~/bin/modelctl add --model "$HOME/LLM_Repository/gemma-4-31B-it-GGUF/gemma-4-31B-it-UD-Q8_K_XL.gguf" \
  --name "Gemma4 31B IT (llama.cpp)"
```

If the GGUF tool is available, context length is detected automatically.
If not, the command warns and uses a safe default.

GGUF tool detection looks for `gguf_dump` or `llama-gguf` on your PATH.

## Switch OpenClaw to the New Model

```bash
agentctl exec openclaw models set llama_cpp/gemma-4-31B-it-UD-Q8_K_XL.gguf
```

Switch back:

```bash
agentctl exec openclaw models set llama_cpp/Qwen3.5-35B-A3B-Q8_0.gguf
```

## See Also

- [Adding a Model Profile](./ADDING_MODEL_PROFILE.md)
- [modelctl Guide](./MODELCTL_GUIDE.md)
- [Configuration](./CONFIGURATION.md)
