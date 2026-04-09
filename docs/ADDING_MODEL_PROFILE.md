# Adding a New Model Profile

**Created**: 2026-02-26
**Updated**: 2026-03-01

- [Adding a New Model Profile](#adding-a-new-model-profile)
  - [Goal](#goal)
  - [1) Start from a template (recommended)](#1-start-from-a-template-recommended)
  - [2) Set required model profile values](#2-set-required-model-profile-values)
  - [3) Launcher creation (automatic)](#3-launcher-creation-automatic)
  - [4) Auto-generate runtime link manifest](#4-auto-generate-runtime-link-manifest)
  - [5) Deploy and verify links](#5-deploy-and-verify-links)
  - [6) Template workflow](#6-template-workflow)
  - [7) Validate profile before start](#7-validate-profile-before-start)
  - [8) Optional: add provider model entry in `.openclaw/openclaw.json`](#8-optional-add-provider-model-entry-in-openclawopenclawjson)
  - [9) Optional: register model in OpenClaw and switch primary](#9-optional-register-model-in-openclaw-and-switch-primary)

## Goal

Add a new model command (example: `MyModel`) using existing `modelctl` architecture.

## 1) Start from a template (recommended)

For model defaults, start by copying one of these:

- Generic LLM template: `scripts/defaults/llm-defaults.sh`
- Generic embedding template: `scripts/defaults/embedding-defaults.sh`
- Closest existing model profile in `scripts/models/` (often faster)

Example:

```bash
cp scripts/models/Qwen3.5.sh scripts/models/MyModel.sh
```

Then edit only model-specific values.

## 2) Set required model profile values

Set at minimum:

- `MODEL_TYPE` (`llm`, `embedding`, stt, or `tts`)
- `MODEL_PROFILE`
- `MODEL`
- `PORT`
- `CTX_SIZE`, `GPU_LAYERS`, `BATCH_SIZE`, `UBATCH_SIZE`
- `THREADS`, `THREADS_BATCH`

LLM-only:

- `MMPROJ` (if multimodal)
- `USE_CUSTOM_TEMPLATE`
- `CHAT_TEMPLATE`

Embedding-only:

- `POOLING`

TTS-only:

- `TTS_PYTHON_BIN` (example `python`)
- `TTS_SERVER_MODULE` (example `mlx_audio.server`)

## 3) Launcher creation (automatic)

You do not need to hardcode model names in `modelctl`.

`scripts/generate-manifest` now auto-creates `scripts/<Profile>` launchers for each `scripts/models/<Profile>.sh` file (as symlinks to `modelctl`).

## 4) Auto-generate runtime link manifest

Runtime link manifest is generated from launcher symlinks:

```bash
~/projects/LLM-Ops-Kit/scripts/generate-manifest
```

`sync-ops-scripts` also runs this automatically before rsync (unless `--no-manifest` is used).

## 5) Deploy and verify links

```bash
/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/deploy-runtime-links.sh
/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/verify-runtime-links.sh
```

Remote:

```bash
ssh <host> '/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/deploy-runtime-links.sh'
ssh <host> '/usr/local/bin/bash ~/projects/LLM-Ops-Kit/scripts/verify-runtime-links.sh'
```

## 6) Template workflow

If reusing stable template:

- point `CHAT_TEMPLATE` to existing canonical template.

If creating a new template:

1. Copy base template from `scripts/templates/`
2. Rename clearly (for example `MyModel-chatml-tools.jinja`)
3. Keep historical-thinking filtering behavior if needed for multi-turn stability
4. Set `CHAT_TEMPLATE` in your model profile
5. Validate with `~/bin/MyModel settings`

## 7) Validate profile before start

```bash
~/bin/MyModel settings
~/bin/MyModel start
~/bin/MyModel status
```

## 8) Optional: add provider model entry in `.openclaw/openclaw.json`

- Add model entry under appropriate provider.
- Start with placeholder id if runtime id is unknown.
- Finalize id after first successful run confirms exact model name/id.

## 9) Optional: register model in OpenClaw and switch primary

OpenClaw tracks model metadata in:

- `~/.openclaw/agents/main/agent/models.json`

To lock the model id (as reported by llama.cpp), use one of:

```bash
~/bin/<Profile> verify
curl -sS http://127.0.0.1:11434/v1/models
```

Then add the model under `providers.llama_cpp.models` (or the relevant provider) using the exact id.

Example entry:

```json
{
  "id": "gemma-4-31B-it-UD-Q8_K_XL.gguf",
  "name": "Gemma4 31B IT (llama.cpp)",
  "api": "openai-completions",
  "reasoning": true,
  "input": ["text", "image"],
  "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
  "contextWindow": 262144,
  "maxTokens": 8192
}
```

Switch the primary model with:

```bash
agentctl exec openclaw models set llama_cpp/<model_id>
```

Example:

```bash
agentctl exec openclaw models set llama_cpp/gemma-4-31B-it-UD-Q8_K_XL.gguf
```
