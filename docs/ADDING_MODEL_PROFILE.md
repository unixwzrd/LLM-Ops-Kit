# Adding a New Model Profile

**Created**: 2026-02-26
**Updated**: 2026-02-26

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

- `MODEL_TYPE` (`llm` or `embedding`)
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

## 3) Add invocation mapping in modelctl

Update `scripts/modelctl`:

- `resolve_model_from_invocation()`
- `load_model_defaults()` case mapping for your profile name
- usage/help text if needed

## 4) Create launcher symlink

Create command launcher in `scripts/`:

```bash
ln -sfn modelctl ~/projects/agent-work/scripts/MyModel
```

## 5) Auto-generate runtime link manifest

Runtime link manifest is generated from launcher symlinks:

```bash
~/projects/agent-work/scripts/generate-manifest
```

`sync-agent-work` also runs this automatically before rsync (unless `--no-manifest` is used).

## 6) Deploy and verify links

```bash
~/bin/deploy-runtime-links.sh
~/bin/verify-runtime-links.sh
```

Remote:

```bash
ssh <host> '/usr/local/bin/bash ~/projects/agent-work/scripts/deploy-runtime-links.sh'
ssh <host> '/usr/local/bin/bash ~/projects/agent-work/scripts/verify-runtime-links.sh'
```

## 7) Template workflow

If reusing stable template:

- point `CHAT_TEMPLATE` to existing canonical template.

If creating a new template:

1. Copy base template from `scripts/templates/`
2. Rename clearly (for example `MyModel-chatml-tools.jinja`)
3. Keep historical-thinking filtering behavior if needed for multi-turn stability
4. Set `CHAT_TEMPLATE` in your model profile
5. Validate with `~/bin/MyModel settings`

## 8) Validate profile before start

```bash
~/bin/MyModel settings
~/bin/MyModel start
~/bin/MyModel status
```

## 9) Optional: add provider model entry in `.openclaw/openclaw.json`

- Add model entry under appropriate provider.
- Start with placeholder id if runtime id is unknown.
- Finalize id after first successful run confirms exact model name/id.
