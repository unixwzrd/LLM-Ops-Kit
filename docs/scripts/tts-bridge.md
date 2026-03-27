# tts-bridge

**Created**: 2026-03-03
**Updated**: 2026-03-25

Run a local OpenAI-compatible TTS bridge that forwards to your MLX Audio server and injects a configured voice clone payload (`model`, `voice`, `ref_audio`, `ref_text`).

The bridge can now:

- rewrite incoming text through a pronunciation dictionary
- map friendly voice names to clone samples and matching transcripts
- load config from a dedicated bridge config directory
- fail loudly when alias-resolved files or config are wrong

```bash
~/bin/tts-bridge [start|stop|restart|status]
```

Default runtime:

- Listen: `127.0.0.1:11440` example only
- Upstream MLX: `http://127.0.0.1:11439/v1` example only

Port note:

- `11440` (bridge) and `11439` (upstream MLX) are examples only, not requirements.
- Any free/open ports will work.
- If you change ports, keep `TTS_BRIDGE_UPSTREAM_BASE` and OpenClaw TTS base URL in sync.

Default voice clone sample:

- `TTS_BRIDGE_REF_AUDIO=$HOME/LLM_Repository/TTS/Samples/speaker-reference-a.wav`
- `TTS_BRIDGE_REF_TEXT=$HOME/LLM_Repository/TTS/Samples/speaker-reference-a.txt`

Default bridge config files:

- `~/.llm-ops/pronounce.json`
- `~/.llm-ops/voice-map.json`

Environment overrides:

- `TTS_BRIDGE_HOST`
- `TTS_BRIDGE_PORT`
- `TTS_BRIDGE_UPSTREAM_BASE`
- `TTS_BRIDGE_MODEL`
- `TTS_BRIDGE_CONFIG_DIR`
- `TTS_BRIDGE_PRONOUNCE_CONFIG`
- `TTS_BRIDGE_VOICE_MAP_CONFIG`
- `TTS_BRIDGE_SAMPLES_DIR`
- `TTS_BRIDGE_LOG_PATH`
- `TTS_BRIDGE_LOG_ROTATE_SECONDS`
- `TTS_BRIDGE_LOG_ROTATE_KEEP`
- `TTS_BRIDGE_VOICE`
  - Required fallback for `CustomVoice` bridge setups unless the caller always supplies `voice`.
  - The bridge forwards clone refs and keeps `voice` for `CustomVoice` requests.
- `TTS_BRIDGE_REF_AUDIO`
- `TTS_BRIDGE_REF_TEXT`
- `TTS_BRIDGE_PYTHON_BIN`
- `LLMOPS_LOG_ROTATE_BYTES`
- `LLMOPS_LOG_ROTATE_KEEP`
- `LLMOPS_LOG_ROTATE_MAX_AGE_DAYS`
- `LLMOPS_BACKUP_KEEP`
- `LLMOPS_BACKUP_MAX_AGE_DAYS`

Status output:

- Reports wrapper PID state plus the live listener PID on the configured port.
- Reports effective `listen` and `upstream` values.
- Prefers upstream `/v1/models` reporting for the active model shown in `status`.
- Reads bridge runtime details from the live `/health` payload instead of reprinting local wrapper defaults.
- Reports resolved config paths for pronunciation, voice map, and sample directory.
- Reports active log path plus time-rotation settings.
- Reports runtime mode, runtime root, and retention policy.
- Probes bridge health via `/health`.
- Probes upstream health via `/v1/models`.
- Returns non-zero when bridge or upstream health is down.

Config resolution precedence:

1. CLI flag
2. matching environment variable
3. `~/.llm-ops/config.env`
4. file derived from `TTS_BRIDGE_CONFIG_DIR`
5. built-in default

Clarification:

- `tts-bridge` is not driven by one dedicated shell config file.
- Wrapper-level settings come from CLI flags and environment.
- Structured bridge data comes from JSON files under `TTS_BRIDGE_CONFIG_DIR`.
- In practice that means:
  - shell/env chooses things like host, port, upstream URL, model path, and config-dir
  - `pronounce.json` and `voice-map.json` provide the bridge-specific structured data

Defaults:

- `config-dir`: `~/.llm-ops`
- `pronounce-config`: `<config-dir>/pronounce.json`
- `voice-map-config`: `<config-dir>/voice-map.json`
- `samples-dir`: `~/LLM_Repository/TTS/Samples`

Pronunciation dictionary behavior:

- loaded once at startup
- applies to every incoming `input` string
- supports single-character and multi-character replacements
- uses longest-match-first scanning
- allows empty-string replacements

Voice map behavior:

- voice alias lookup is case-insensitive
- an optional top-level `defaults` object can declare `sample_dir`, `speaker`, and `sample`
- alias entries require `speaker` and `sample`
- alias sample paths resolve relative to alias `sample_dir`, then `defaults.sample_dir`, then the bridge `samples-dir`
- alias-derived `ref_audio` and `ref_text` are only used when the request does not already provide explicit `ref_audio` or `ref_text`
- if no alias matches and no explicit refs are sent, `defaults.sample` and `defaults.speaker` can act as the fallback clone voice
- if no voice is provided by the request, alias, defaults, or bridge env, the bridge leaves `voice` unset instead of inventing one
- transcript defaults to the sample basename with `.txt`
- missing alias sample or transcript is a hard request failure

Allowed empty defaults:

- missing `pronounce.json` loads as an empty map
- missing `voice-map.json` loads as an empty map
- unknown voice aliases are ignored

Startup and failure behavior:

- malformed JSON causes startup failure with the exact file path and parse error
- malformed alias entries cause startup failure
- missing local samples directory is logged as a warning and startup continues
- alias-resolved missing files cause request failure with the exact missing path

Startup logging:

- startup logs no longer dump a JSON config blob
- use `~/bin/tts-bridge status` as the canonical human-readable runtime summary
- routine `/health` probes are not written into the bridge log

Log rotation behavior:

- the active bridge log path stays stable at `tts-bridge.log`
- older files rotate to `.0.log`, `.1.log`, and so on
- `TTS_BRIDGE_LOG_ROTATE_SECONDS` defaults to `86400` seconds
- `TTS_BRIDGE_LOG_ROTATE_KEEP` defaults to `5`

Example `pronounce.json`:

```json
{
  "/": " slash ",
  "*": " star ",
  "[": " open bracket ",
  "]": " close bracket ",
  "{": " open brace ",
  "}": " close brace ",
  "\"": "",
  "'": ""
}
```

See also:

- [`examples/tts/pronounce.example.json`](../../examples/tts/pronounce.example.json)

Example `voice-map.json`:

```json
{
  "defaults": {
    "sample_dir": ".",
    "speaker": "serena",
    "sample": "speaker-reference-b.wav"
  },
  "Sol": {
    "speaker": "Chelsie",
    "sample": "speaker-reference-a.wav"
  },
  "Guide": {
    "speaker": "serena",
    "sample": "speaker-reference-b.wav"
  }
}
```

See also:

- [`examples/tts/voice-map.example.json`](../../examples/tts/voice-map.example.json)

Quick bootstrap:

```bash
mkdir -p ~/.llm-ops
cp /path/to/LLM-Ops-Kit/examples/tts/pronounce.example.json ~/.llm-ops/pronounce.json
cp /path/to/LLM-Ops-Kit/examples/tts/voice-map.example.json ~/.llm-ops/voice-map.json
```

Smoke test with a symbol-heavy payload:

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

Health check:

```bash
curl -sS http://127.0.0.1:11440/health | jq
```

What to expect from the smoke test:

- the bridge should resolve `voice: "Guide"` through `voice-map.json`
- `/health` should report the resolved config file paths and entry counts
- the bridge log should show that input preprocessing was applied
- the upstream payload should receive `slash`, `open bracket`, and other replacements from `pronounce.json`

Compatibility notes:

- Unsupported OpenAI-style output formats such as `opus` and `ogg` are normalized to `wav` before forwarding to MLX Audio.
- In this deployment, the bridge forwards `ref_audio` and `ref_text` as server-side paths on the MLX host.
- Correct cloning with `CustomVoice` depends on the upstream `mlx-audio` path resolving `ref_text` server-side and preferring the ICL clone path when clone refs are present.

OpenClaw wiring:

```bash
export OPENAI_TTS_BASE_URL=http://127.0.0.1:11440/v1
```

That port is an example only. Use the bridge port from your `~/.llm-ops/config.env`.

Then set `messages.tts.provider` to `openai` in `~/.openclaw/openclaw.json`.
