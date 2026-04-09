# modelctl Guide

Back: [docs/INDEX.md](./INDEX.md)

**Created**: 2026-02-26
**Updated**: 2026-03-06

- [modelctl Guide](#modelctl-guide)
  - [Purpose](#purpose)
  - [Commands](#commands)
  - [Precedence Order (highest -\> lowest)](#precedence-order-highest---lowest)
  - [How model type is selected](#how-model-type-is-selected)
  - [Template behavior](#template-behavior)
  - [Sampling behavior](#sampling-behavior)
  - [Validation rules](#validation-rules)
  - [Status behavior](#status-behavior)
  - [Where logs/pids live](#where-logspids-live)

## Purpose

`modelctl` is the canonical launcher used by runtime commands like `Qwen3`, `Qwen3.5`, and `BGEm3`.
Any launcher name is supported as long as `scripts/models/<Launcher>.sh` exists.

## Commands

```bash
~/bin/<ModelProfile> [start|stop|restart|status|settings|verify|test]
~/bin/modelctl <ModelProfile> [start|stop|restart|status|settings|verify|test]
~/bin/modelctl add --model <path> --name <label>
```

- `status`: checks pidfile, validates pid is still running, validates process command shape via `ps`, and does a fast API probe.
- `verify`: checks process status and queries `/v1/models` to print reported model IDs.
- `test`: runs a minimal live request for the model type:
  - `llm`: `/v1/chat/completions`
  - `embedding`: `/v1/embeddings`
  - `tts`: `/v1/audio/speech`

`modelctl add` registers a model in OpenClaw with optional GGUF metadata extraction, then prints a command to switch OpenClaw to it.

## modelctl add (what it does)

`modelctl add` is designed for non-technical use. It can infer values from the GGUF when possible.

What it tries, in order:

1. Use `--model` to infer the model id from the filename.
2. If a GGUF tool is available (`gguf_dump` or `llama-gguf`), extract context length.
3. If no GGUF tool is present, warn and fall back to safe defaults.
4. If no `--id` or `--model` was provided, query `/v1/models` and pick the first id.

Output:

- Writes an entry into `~/.openclaw/agents/main/agent/models.json`.
- Prints the exact `agentctl exec openclaw models set ...` command to switch OpenClaw to the model.

Tip: you can always override with `--ctx` and `--max-tokens` if you want exact values.

## verify and test (what they do)

- `verify` hits `/v1/models` and prints the reported model ids so you can confirm what is actually running.
- `test` sends a small, real request:
  - LLM: asks for a single-word reply
  - Embedding: requests a small embedding vector
  - TTS: generates a tiny WAV sample and reports its size

## Precedence Order (highest -> lowest)

`modelctl` loads settings in this order:

1. External environment variables (already exported)
2. `~/.llm-ops/config.env`
3. `~/.llm-ops/config/<Profile>.env`
4. Model profile defaults (`scripts/models/<Profile>.sh`)
5. Model-type defaults (`scripts/defaults/llm-defaults.sh`, `scripts/defaults/embedding-defaults.sh`, or `scripts/defaults/tts-defaults.sh`)
6. Global llama defaults (`scripts/defaults/llama-defaults.sh`) for llama-based model types only

This works because defaults use `VAR="${VAR:-...}"` and do not overwrite values already set.

Per-model override files use the same shell layout as the shipped model profile files, so you can copy a profile into `~/.llm-ops/config/<Profile>.env` and adjust only the values you want to change.

If `~/.llm-ops/config/<Profile>.env` does not exist when you run a model-specific launcher, `modelctl` now auto-copies the shipped profile there and prints a notice. That gives the user a local file to edit without touching the repo copy.

## How model type is selected

- `MODEL_TYPE=llm` uses LLM path (template/sampling flags, optional `MMPROJ`).
- `MODEL_TYPE=embedding` uses embedding path (`--embedding`, `--pooling`).
- `MODEL_TYPE=tts` uses MLX Audio server path (`python -m mlx_audio.server`).

## Template behavior

For LLM profiles:

- `USE_CUSTOM_TEMPLATE=1` enables `--jinja --chat-template-file <path>`.
- `CHAT_TEMPLATE` must point to an existing file.

For embedding profiles:

- Template flags are ignored.

## Sampling behavior

If these are set, `modelctl` passes them to llama-server:

- `TEMP`
- `TOP_P`
- `TOP_K`
- `MIN_P`
- `PRESENCE_PENALTY`
- `REPEAT_PENALTY`

Set these values directly in `~/.llm-ops/config.env`, `~/.llm-ops/config/<Profile>.env`, or your exported environment.

## Validation rules

`modelctl` validates required settings before start:

- Common: `MODEL_PROFILE`, `MODEL`, `MODEL_TYPE`, `PORT`, `HOST`, `THREADS`, `THREADS_BATCH`, `CTX_SIZE`, `GPU_LAYERS`, `BATCH_SIZE`, `UBATCH_SIZE`
- LLM with template enabled: `CHAT_TEMPLATE`
- Embedding: `POOLING`
- TTS: `TTS_PYTHON_BIN`, `TTS_SERVER_MODULE`

## Status behavior

`status` now reports:

- Runtime line (`running`, `stale`, `stopped`, or `pid mismatch`)
- PID and log file path
- `started_at` from model state file when available
- API probe result (`ok`/`failed`) against `http://<HOST>:<PORT>/v1/models`

## Where logs/pids live

- LLM/embedding PID name: `llama-$MODEL_PROFILE`
- LLM/embedding log file: `$LLMOPS_LOG_DIR/llama-server-$MODEL_PROFILE.log`
- TTS PID name: `tts-$MODEL_PROFILE`
- TTS log file: `$LLMOPS_LOG_DIR/tts-server-$MODEL_PROFILE.log`
- State file: `$LLMOPS_RUN_DIR/<pid_name>.state`

Use `status` to see active pid and log path.

## See Also

- [Adding a Model Profile](./ADDING_MODEL_PROFILE.md)
- [Switching Models and Agents](./SWITCHING.md)
- [Configuration](./CONFIGURATION.md)
