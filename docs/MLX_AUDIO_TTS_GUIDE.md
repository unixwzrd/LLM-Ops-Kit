# MLX Audio TTS Guide

**Created**: 2026-03-02  
**Updated**: 2026-07-16

- [MLX Audio TTS Guide](#mlx-audio-tts-guide)
  - [Purpose](#purpose)
  - [Requirements](#requirements)
  - [Model Recommendation](#model-recommendation)
  - [Start the TTS Server](#start-the-tts-server)
  - [API Smoke Test](#api-smoke-test)
  - [Bridge for Agent TTS](#bridge-for-agent-tts)
  - [Bridge Configuration](#bridge-configuration)
  - [Bridge Dictionaries](#bridge-dictionaries)
  - [Reference Voice Workflow](#reference-voice-workflow)
  - [Best Practices for Reference Samples](#best-practices-for-reference-samples)
  - [Known Packaging Gotchas](#known-packaging-gotchas)
  - [Troubleshooting](#troubleshooting)

## Purpose

Provide a repeatable local TTS path through the OpenAI-compatible API. Reference
audio must be owned by the operator or used with the speaker's permission.

## Requirements

- Python 3.9+
- `mlx-audio` installed in the active Python environment
- A local model directory for Qwen3-TTS Base
- Toolkit profile `Qwen3TTS` configured in `scripts/models/Qwen3TTS.sh`

Upstream links:

- MLX Audio: <https://github.com/Blaizzy/mlx-audio>
- Qwen3-TTS 0.6B Base (MLX): <https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit>

Temporary compatibility note:

- Until upstream `mlx-audio` PR `#558` merges, the validated source for this deployment is:
  - <https://github.com/unixwzrd/mlx-audio>
  - upstream PR: <https://github.com/Blaizzy/mlx-audio/pull/558>

## Model Recommendation

Default recommendation for most systems:

- `Qwen3-TTS-12Hz-0.6B-Base-8bit`

Why:

- Supports reference-conditioned speech with operator-authorized samples
- Lower memory use than 1.7B variants
- Fast enough for iterative testing

## Start the TTS Server

```bash
llmops Qwen3TTS settings
llmops Qwen3TTS start
llmops Qwen3TTS status
llmops Qwen3TTS verify
```

Defaults:

- Listen host: `127.0.0.1`
- Listen port: `11439`

Port note:

- `11439` is just the default example.
- Any free/open port is valid, as long as the same port is used consistently in your model startup and bridge settings.

Override via environment (optional):

- `HOST`, `PORT`
- `TTS_PYTHON_BIN`, `TTS_SERVER_MODULE`
- `TTS_RUNTIME_PATH` for utilities such as `ffmpeg`

## API Smoke Test

```bash
curl -sS http://127.0.0.1:11439/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "'"$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-Base-8bit"'",
    "input": "Hello from local MLX TTS.",
    "response_format": "wav"
  }' \
  --output /tmp/tts-smoke.wav
```

If the MLX TTS server runs on a different machine, replace `127.0.0.1` with your remote model host. The URL above is the direct upstream TTS server, not the local `tts-bridge`.

## Bridge for Agent TTS

Use `tts-bridge` so Hermes or OpenClaw can issue OpenAI-style TTS requests while
the bridge injects MLX-specific fields (`model`, `ref_audio`, `ref_text`).

Important Base-model note:

- The validated path uses the Base 0.6B 8-bit model with reference audio and a
  matching transcript. Friendly voice names are bridge aliases, not built-in
  model speakers.
- WAV needs no external encoder. MP3/FLAC requires `ffmpeg` in the managed TTS
  process PATH.
- Unsupported response formats such as `opus` and `ogg` are normalized to `wav`.

Operationally, this behaves like `model-proxy`: start/stop/restart/status via a wrapper script with PID and log tracking.

```bash
llmops tts-bridge start
llmops tts-bridge status
```

Then route the agent's OpenAI-compatible TTS provider to the bridge.

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
        "model": "${HOME}/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-Base-8bit",
        "voice": "serena"
      }
    }
  }
}
```

Treat the `11440` value above as an example only. Use whatever local bridge port you configured in `~/.config/llm-ops/config.env`.

Hermes equivalent:

```yaml
tts:
  provider: openai
  openai:
    base_url: http://127.0.0.1:11439/v1
    model: /path/to/Qwen3-TTS-12Hz-0.6B-Base-8bit
    voice: voice-a
```

## Bridge Configuration

For normal installed-runtime operation, configure `tts-bridge` in:

- `~/.config/llm-ops/config.env`

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
export TTS_BRIDGE_UPSTREAM_BASE=http://<remote-mlx-host>:11439/v1
export TTS_BRIDGE_MODEL=$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-Base-8bit
export TTS_BRIDGE_CONFIG_DIR=$HOME/.llm-ops
export TTS_BRIDGE_SAMPLES_DIR=$HOME/LLM_Repository/TTS/Samples
export TTS_BRIDGE_VOICE=Guide
export TTS_BRIDGE_REF_AUDIO=$HOME/LLM_Repository/TTS/Samples/speaker-reference-a.wav
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

- maps a friendly incoming voice name to an authorized reference sample
- supports a top-level `defaults` block for shared `sample_dir` and fallback `sample`
- derives the transcript path from the sample basename unless `ref_text` is explicitly set in the alias
- `sample` is required; `ref_text` is optional
- is case-insensitive on lookup
- is only used when the request does not already supply explicit `ref_audio` and `ref_text`
- if nothing supplies a direct non-alias voice, the bridge leaves `voice` unset rather than silently choosing one in code

Example:

```json
{
  "defaults": {
    "sample_dir": ".",
    "sample": "speaker-reference-a.wav"
  },
  "Sol": {
    "sample": "speaker-reference-b.wav"
  },
  "Guide": {
    "sample": "speaker-reference-a.wav"
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
- missing local sample directory is logged as a warning and startup continues
- alias-resolved sample and transcript paths may be valid only on the upstream MLX host; if they are missing locally on the bridge machine, the bridge now logs a warning and still forwards the path strings upstream

The bridge `/health` endpoint reports the resolved config directory, config file paths, whether the files exist, entry counts, and the resolved samples directory.

Bootstrap the config files:

```bash
mkdir -p ~/.llm-ops
cp /path/to/LLM-Ops-Kit/examples/tts/pronounce.example.json ~/.llm-ops/pronounce.json
cp /path/to/LLM-Ops-Kit/examples/tts/voice-map.example.json ~/.llm-ops/voice-map.json
```

Start the bridge:

```bash
llmops tts-bridge start
llmops tts-bridge status
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
    "input": "Read /tmp/test[1].wav and say Guide clearly.",
    "voice": "Guide",
    "response_format": "wav"
  }' \
  --output /tmp/tts-bridge-guide.wav
```

If that passes, confirm:

- `llmops tts-bridge status` reports bridge health as `ok`
- `/health` shows the resolved config and sample paths you expect
- the output file `/tmp/tts-bridge-guide.wav` exists
- the bridge stderr log shows input preprocessing and alias resolution activity

Bridge log rotation:

- the active bridge log stays at `~/.local/state/llm-ops/logs/tts-bridge.log`
- older bridge logs rotate to `.0.log`, `.1.log`, and so on
- `TTS_BRIDGE_LOG_ROTATE_SECONDS` defaults to `86400`
- `TTS_BRIDGE_LOG_ROTATE_KEEP` defaults to `5`

## Reference Voice Workflow

Use a `.wav` and a matching transcript `.txt` with the same basename:

- `speaker-reference-a.wav`
- `speaker-reference-a.txt`

Example request:

```bash
AUDIO="$HOME/LLM_Repository/TTS/Samples/speaker-reference-a.wav"
TEXT="${AUDIO%.wav}.txt"
MODEL="$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-Base-8bit"
OUT="/tmp/test-tts-reference.wav"

curl -sS http://<remote-mlx-host>:11439/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg model "$MODEL" \
    --arg input "Hello, this is a quick reference-voice check." \
    --arg ref_audio "$AUDIO" \
    --arg ref_text "$TEXT" \
    --arg response_format "wav" \
    '{model:$model,input:$input,ref_audio:$ref_audio,ref_text:$ref_text,response_format:$response_format}')" \
  --output "$OUT"
```

For this deployment, `ref_audio` and `ref_text` are server-side paths on the MLX host. They do not need to exist on the bridge machine. Do not inline the transcript text into the JSON payload.

Friendly names belong in `voice-map.json`; keep repository examples neutral and
keep private filenames in host-local configuration.

## Best Practices for Reference Samples

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
- Confirm the model is the Base variant when using reference audio and text.
- Confirm the transcript file exists on the MLX host, is non-empty, and matches the sample.
- Check server log:
  - `~/.openclaw/logs/tts-server-Qwen3TTS.log`

If server is not reachable:

```bash
llmops Qwen3TTS status
lsof -nP -iTCP:11439 -sTCP:LISTEN
```

Back to script-level command docs:

- [`docs/scripts/tts.md`](./scripts/tts.md)
