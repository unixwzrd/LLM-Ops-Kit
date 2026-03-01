# modelctl Guide

**Created**: 2026-02-26
**Updated**: 2026-02-28

- [modelctl Guide](#modelctl-guide)
  - [Purpose](#purpose)
  - [Commands](#commands)
  - [Precedence Order (highest -\> lowest)](#precedence-order-highest---lowest)
  - [How model type is selected](#how-model-type-is-selected)
  - [Template behavior](#template-behavior)
  - [Sampling behavior](#sampling-behavior)
  - [Validation rules](#validation-rules)
  - [Where logs/pids live](#where-logspids-live)

## Purpose

`modelctl` is the canonical launcher used by runtime commands like `Qwen3`, `Qwen3.5`, and `BGEen`.
Any launcher name is supported as long as `scripts/models/<Launcher>.sh` exists.

## Commands

```bash
~/bin/<ModelProfile> [start|stop|restart|status|settings]
```

## Precedence Order (highest -> lowest)

`modelctl` loads settings in this order:

1. External environment variables (already exported)
2. Model profile defaults (`scripts/models/<Profile>.sh`)
3. Model-type defaults (`scripts/defaults/llm-defaults.sh` or `scripts/defaults/embedding-defaults.sh`)
4. Global llama defaults (`scripts/defaults/llama-defaults.sh`)

This works because defaults use `VAR="${VAR:-...}"` and do not overwrite values already set.

## How model type is selected

- `MODEL_TYPE=llm` uses LLM path (template/sampling flags, optional `MMPROJ`).
- `MODEL_TYPE=embedding` uses embedding path (`--embedding`, `--pooling`).

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

Model profiles can implement preset selectors (for example `QWEN35_PRESET`) that set these values.

## Validation rules

`modelctl` validates required settings before start:

- Common: `MODEL_PROFILE`, `MODEL`, `MODEL_TYPE`, `PORT`, `HOST`, `THREADS`, `THREADS_BATCH`, `CTX_SIZE`, `GPU_LAYERS`, `BATCH_SIZE`, `UBATCH_SIZE`
- LLM with template enabled: `CHAT_TEMPLATE`
- Embedding: `POOLING`

## Where logs/pids live

- PID name: `llama-$MODEL_PROFILE`
- Log file: `$OPENCLAW_LOG_DIR/llama-server-$MODEL_PROFILE.log`

Use `status` to see active pid and log path.
