# MLX Audio TTS Guide

**Created**: 2026-03-02  
**Updated**: 2026-03-18

- [MLX Audio TTS Guide](#mlx-audio-tts-guide)
  - [Purpose](#purpose)
  - [Requirements](#requirements)
  - [Model Recommendation](#model-recommendation)
  - [Start the TTS Server](#start-the-tts-server)
  - [API Smoke Test](#api-smoke-test)
  - [Bridge for OpenClaw TTS](#bridge-for-openclaw-tts)
  - [Bridge Configuration](#bridge-configuration)
  - [Bridge Dictionaries](#bridge-dictionaries)
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

Temporary compatibility note:

- Until upstream `mlx-audio` PR `#558` merges, the validated source for this deployment is:
  - <https://github.com/unixwzrd/mlx-audio>
  - upstream PR: <https://github.com/Blaizzy/mlx-audio/pull/558>

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

- The validated clone path for this deployment uses a `CustomVoice` model together with clone refs.
- `tts-bridge` forwards `model`, `voice`, `ref_audio`, and `ref_text`, while the upstream `mlx-audio` server resolves `ref_text` from a server-side path and routes clone-ref requests through the ICL path.
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

## Bridge Configuration

For normal installed-runtime operation, configure `tts-bridge` in:

- `~/.llm-ops/config.env`

The main bridge settings are:

- `TTS_BRIDGE_HOST`
- `TTS_BRIDGE_PORT`
- `TTS_BRIDGE_UPSTREAM_BASE`
- `TTS_BRIDGE_MODEL`
- `TTS_BRIDGE_CONFIG_DIR`
- `TTS_BRIDGE_PRONOUNCE_CONFIG`
- `TTS_BRIDGE_VOICE_MAP_CONFIG`
- `TTS_BRIDGE_SAMPLES_DIR`
- `TTS_BRIDGE_VOICE`
- `TTS_BRIDGE_REF_AUDIO`
- `TTS_BRIDGE_REF_TEXT`
- `TTS_BRIDGE_PYTHON_BIN`

Example:

```bash
export TTS_BRIDGE_HOST=127.0.0.1
export TTS_BRIDGE_PORT=11440
export TTS_BRIDGE_UPSTREAM_BASE=http://10.0.0.67:11439/v1
export TTS_BRIDGE_MODEL=$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit
export TTS_BRIDGE_CONFIG_DIR=$HOME/.llm-ops
export TTS_BRIDGE_SAMPLES_DIR=$HOME/LLM_Repository/TTS/Samples
export TTS_BRIDGE_VOICE=Faith
export TTS_BRIDGE_REF_AUDIO=$HOME/LLM_Repository/TTS/Samples/Mia-Faith-Sample.wav
export TTS_BRIDGE_REF_TEXT="${TTS_BRIDGE_REF_AUDIO%.*}.txt"
```

Path precedence for bridge config:

1. CLI flag
2. matching environment variable
3. file derived from `TTS_BRIDGE_CONFIG_DIR`
4. built-in default

Default file names:

- `~/.llm-ops/pronounce.json`
- `~/.llm-ops/voice-map.json`

OpenClaw itself still points at the local bridge through:

- `OPENAI_TTS_BASE_URL` in `~/.openclaw/.env`

For command-level details, see:

- [`docs/scripts/tts-bridge.md`](./scripts/tts-bridge.md)

## Bridge Dictionaries

The bridge supports two optional JSON dictionaries loaded once at startup.

`pronounce.json`:

- rewrites incoming TTS text before it reaches MLX Audio
- supports symbol substitutions and later word or phrase substitutions
- uses longest-match-first scanning
- applies to every request

Example:

```json
{
  "/": " slash ",
  "*": " star ",
  "[": " open bracket ",
  "]": " close bracket ",
  "{": " open brace ",
  "}": " close brace "
}
```

`voice-map.json`:

- maps a friendly incoming voice name to a real speaker plus clone sample
- supports a top-level `defaults` block for shared `sample_dir`, fallback `speaker`, and fallback `sample`
- derives the transcript path from the sample basename unless `ref_text` is explicitly set in the alias
- is case-insensitive on lookup
- is only used when the request does not already supply explicit `ref_audio` and `ref_text`
- if nothing supplies a speaker, the bridge leaves `voice` unset rather than silently choosing one in code

Example:

```json
{
  "defaults": {
    "sample_dir": ".",
    "speaker": "serena",
    "sample": "Mia-Faith-Prof-Emotive-20s-Sample-Mastered-01.wav"
  },
  "Faith": {
    "speaker": "serena",
    "sample": "Mia-Faith-Prof-Emotive-20s-Sample-Mastered-01.wav"
  },
  "Serifina": {
    "speaker": "serena",
    "sample": "Mia-Serifina-Sensual-Emotive-20s-Sample-Mastered-02.wav"
  }
}
```

Repo examples:

- [`examples/tts/pronounce.example.json`](../examples/tts/pronounce.example.json)
- [`examples/tts/voice-map.example.json`](../examples/tts/voice-map.example.json)

Fail-fast behavior:

- missing config files are allowed and load as empty maps
- malformed JSON fails startup
- malformed alias entries fail startup
- invalid sample directory fails startup
- alias-resolved missing sample or transcript fails the request with an explicit error

The bridge `/health` endpoint reports the resolved config directory, config file paths, whether the files exist, entry counts, and the resolved samples directory.

Bootstrap the config files:

```bash
mkdir -p ~/.llm-ops
cp /path/to/LLM-Ops-Kit/examples/tts/pronounce.example.json ~/.llm-ops/pronounce.json
cp /path/to/LLM-Ops-Kit/examples/tts/voice-map.example.json ~/.llm-ops/voice-map.json
```

Start the bridge:

```bash
~/bin/tts-bridge start
~/bin/tts-bridge status
```

Bridge health check:

```bash
curl -sS http://127.0.0.1:11440/health | jq
```

Bridge speech smoke test:

```bash
curl -sS http://127.0.0.1:11440/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "input": "Read /tmp/test[1].wav and say Faith/Serifina clearly.",
    "voice": "Faith",
    "response_format": "wav"
  }' \
  --output /tmp/tts-bridge-faith.wav
```

If that passes, confirm:

- `~/bin/tts-bridge status` reports bridge health as `ok`
- `/health` shows the resolved config and sample paths you expect
- the output file `/tmp/tts-bridge-faith.wav` exists
- the bridge stderr log shows input preprocessing and alias resolution activity

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

For the current MLX build, these are the predefined speaker names reported for speaker-mode requests:

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
- Confirm the model is a `CustomVoice` model when using clone refs in this deployment.
- Confirm the transcript file exists on the MLX host, is non-empty, and matches the sample.
- Check server log:
  - `~/.openclaw/logs/tts-server-Qwen3TTS.log`

If server is not reachable:

```bash
~/bin/Qwen3TTS status
lsof -nP -iTCP:11439 -sTCP:LISTEN
```

Back to script-level command docs:

- [`docs/scripts/tts.md`](./scripts/tts.md)
