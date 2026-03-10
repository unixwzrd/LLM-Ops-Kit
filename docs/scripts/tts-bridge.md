# tts-bridge

**Created**: 2026-03-03
**Updated**: 2026-03-09

Run a local OpenAI-compatible TTS bridge that forwards to your MLX Audio server and injects a configured voice clone payload (`model`, `voice`, `ref_audio`, `ref_text`).

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

- `TTS_BRIDGE_REF_AUDIO=$HOME/LLM_Repository/TTS/Samples/Mia-Faith-Prof-Emotive-60s-Sample-Mastered-01.wav`
- `TTS_BRIDGE_REF_TEXT=$HOME/LLM_Repository/TTS/Samples/Mia-Faith-Prof-Emotive-60s-Sample-Mastered-01.txt`

Environment overrides:

- `TTS_BRIDGE_HOST`
- `TTS_BRIDGE_PORT`
- `TTS_BRIDGE_UPSTREAM_BASE`
- `TTS_BRIDGE_MODEL`
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
- Reports runtime mode, runtime root, and retention policy.
- Probes bridge health via `/health`.
- Probes upstream health via `/v1/models`.
- Returns non-zero when bridge or upstream health is down.

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
