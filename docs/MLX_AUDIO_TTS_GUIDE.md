# MLX Audio TTS Guide

**Created**: 2026-03-02  
**Updated**: 2026-03-02

- [MLX Audio TTS Guide](#mlx-audio-tts-guide)
  - [Purpose](#purpose)
  - [Requirements](#requirements)
  - [Model Recommendation](#model-recommendation)
  - [Start the TTS Server](#start-the-tts-server)
  - [API Smoke Test](#api-smoke-test)
  - [Voice Clone Workflow](#voice-clone-workflow)
  - [Best Practices for Clone Samples](#best-practices-for-clone-samples)
  - [Troubleshooting](#troubleshooting)

## Purpose

Provide a simple, repeatable path to run local TTS with `mlx-audio`, and use voice cloning through the OpenAI-compatible API used by this toolkit.

## Requirements

- Python 3.9+
- `mlx-audio` installed in the active Python environment
- A local model directory for Qwen3-TTS CustomVoice
- Toolkit profile `Qwen3TTS` configured in `scripts/models/Qwen3TTS.sh`

Upstream links:

- MLX Audio: <https://github.com/Blaizzy/mlx-audio>
- Qwen3-TTS 0.6B CustomVoice (MLX): <https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit>

## Model Recommendation

Default recommendation for most systems:

- `Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit`

Why:

- Good quality for local voice clone checks
- Lower memory use than 1.7B variants
- Fast enough for iterative testing

## Start the TTS Server

```bash
~/bin/Qwen3TTS settings
~/bin/Qwen3TTS start
~/bin/Qwen3TTS status
~/bin/Qwen3TTS verify
```

Defaults:

- Listen host: `127.0.0.1`
- Listen port: `18081`

Override via environment (optional):

- `OPENCLAW_TTS_HOST`
- `OPENCLAW_TTS_PORT`
- `OPENCLAW_TTS_PYTHON`
- `OPENCLAW_TTS_MODULE`

## API Smoke Test

```bash
curl -sS http://127.0.0.1:18081/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "'"$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"'",
    "input": "Hello from local MLX TTS.",
    "response_format": "wav"
  }' \
  --output /tmp/tts-smoke.wav
```

## Voice Clone Workflow

Use a `.wav` and a matching transcript `.txt` with the same basename:

- `Mia-Faith-Sample.wav`
- `Mia-Faith-Sample.txt`

Example request:

```bash
AUDIO="$HOME/LLM_Repository/TTS/Samples/Mia-Faith-Sample.wav"
TEXT="${AUDIO%.wav}.txt"
MODEL="$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
OUT="/tmp/mia-clone.wav"

REF_TEXT="$(cat "$TEXT")"

curl -sS http://127.0.0.1:18081/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg model "$MODEL" \
    --arg input "Hey Mike, this is a quick clone check." \
    --arg ref_audio "$AUDIO" \
    --arg ref_text "$REF_TEXT" \
    --arg response_format "wav" \
    '{model:$model,input:$input,ref_audio:$ref_audio,ref_text:$ref_text,response_format:$response_format}')" \
  --output "$OUT"
```

## Best Practices for Clone Samples

- Keep a short sample set for routine operations (20-45 seconds).
- Keep longer samples separately for quality comparisons.
- Ensure transcript text exactly matches sample speech.
- Avoid heavy post-processing that changes voice identity.

## Troubleshooting

If `/v1/audio/speech` returns 500:

- Confirm model path exists and is readable.
- Confirm the model is a `CustomVoice` model when using `ref_audio`.
- Confirm transcript file is non-empty and matches the sample.
- Check server log:
  - `~/.openclaw/logs/tts-server-Qwen3TTS.log`

If server is not reachable:

```bash
~/bin/Qwen3TTS status
lsof -nP -iTCP:18081 -sTCP:LISTEN
```

Back to script-level command docs:

- [`docs/scripts/tts.md`](./scripts/tts.md)
