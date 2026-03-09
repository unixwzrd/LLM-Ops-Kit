# MLX Audio TTS Guide

**Created**: 2026-03-02  
**Updated**: 2026-03-03

- [MLX Audio TTS Guide](#mlx-audio-tts-guide)
  - [Purpose](#purpose)
  - [Requirements](#requirements)
  - [Model Recommendation](#model-recommendation)
  - [Start the TTS Server](#start-the-tts-server)
  - [API Smoke Test](#api-smoke-test)
  - [Bridge for OpenClaw TTS](#bridge-for-openclaw-tts)
  - [Voice Clone Workflow](#voice-clone-workflow)
  - [Best Practices for Clone Samples](#best-practices-for-clone-samples)
  - [Known Packaging Gotchas](#known-packaging-gotchas)
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
- Listen port: `11439`

Port note:

- `11439` is just the default example.
- Any free/open port is valid, as long as the same port is used consistently in your model startup and bridge settings.

Override via environment (optional):

- `LLMOPS_TTS_HOST`
- `LLMOPS_TTS_PORT`
- `LLMOPS_TTS_PYTHON`
- `LLMOPS_TTS_MODULE`

## API Smoke Test

```bash
curl -sS http://127.0.0.1:11439/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "'"$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"'",
    "input": "Hello from local MLX TTS.",
    "response_format": "wav"
  }' \
  --output /tmp/tts-smoke.wav
```

## Bridge for OpenClaw TTS

Use `tts-bridge` so OpenClaw can keep using OpenAI-style TTS requests while your local bridge injects MLX-specific fields (`model`, `voice`, `ref_audio`, `ref_text`).

Important `CustomVoice` note:

- Current `mlx_audio` `CustomVoice` requests require `voice`, even when `ref_audio` and `ref_text` are present.
- The bridge keeps clone refs and injects `voice` from the incoming request or `TTS_BRIDGE_VOICE`.
- Unsupported response formats such as `opus` and `ogg` are normalized to `wav`.

Operationally, this behaves like `model-proxy`: start/stop/restart/status via a wrapper script with PID and log tracking.

```bash
~/bin/tts-bridge start
~/bin/tts-bridge status
```

Then route OpenClaw TTS to the bridge:

```bash
export OPENAI_TTS_BASE_URL=http://127.0.0.1:11440/v1
```

Bridge port note:

- `11440` is an example only, not a required default.
- You can use any free/open port for the bridge; just update `messages.tts.openai.baseUrl` to match.

And set provider in `~/.openclaw/openclaw.json`:

```json
{
  "messages": {
    "tts": {
      "provider": "openai",
      "openai": {
        "baseUrl": "http://127.0.0.1:11440/v1",
        "model": "${HOME}/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit",
        "voice": "serena"
      }
    }
  }
}
```

Treat the `11440` value above as an example only. Use whatever local bridge port you configured in `~/.llm-ops/config.env`.

## Voice Clone Workflow

Use a `.wav` and a matching transcript `.txt` with the same basename:

- `Mia-Faith-Sample.wav`
- `Mia-Faith-Sample.txt`

Example request:

```bash
AUDIO="$HOME/LLM_Repository/TTS/Samples/Mia-Faith-Sample.wav"
TEXT="${AUDIO%.wav}.txt"
MODEL="$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
VOICE="serena"
OUT="/tmp/test-tts-clone.wav"

curl -sS http://10.0.0.67:11439/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg model "$MODEL" \
    --arg input "Hey Mike, this is a quick clone check." \
    --arg voice "$VOICE" \
    --arg ref_audio "$AUDIO" \
    --arg ref_text "$TEXT" \
    --arg response_format "wav" \
    '{model:$model,input:$input,voice:$voice,ref_audio:$ref_audio,ref_text:$ref_text,response_format:$response_format}')" \
  --output "$OUT"
```

For this deployment, `ref_audio` and `ref_text` are server-side paths on the MLX host. Do not inline the transcript text into the JSON payload.

Supported speaker names for the current Qwen3TTS CustomVoice setup:

- `serena`
- `vivian`
- `uncle_fu`
- `ryan`
- `aiden`
- `ono_anna`
- `sohee`
- `eric`
- `dylan`

## Best Practices for Clone Samples

- Keep a short sample set for routine operations (20-45 seconds).
- Keep longer samples separately for quality comparisons.
- Ensure transcript text exactly matches sample speech.
- Avoid heavy post-processing that changes voice identity.

## Known Packaging Gotchas

`mlx-audio` currently may install without all runtime server dependencies in some environments.

Observed missing packages during real startup testing:

- `uvicorn`
- `webrtcvad`
- `fastapi`
- `python-multipart`

Recommended bootstrap after `pip install mlx-audio`:

```bash
python -m pip install -U uvicorn webrtcvad fastapi python-multipart
```

If you maintain a local fork/clone of `mlx-audio`, update its `pyproject.toml` so these dependencies are part of the base install set for server mode.

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
lsof -nP -iTCP:11439 -sTCP:LISTEN
```

Back to script-level command docs:

- [`docs/scripts/tts.md`](./scripts/tts.md)
