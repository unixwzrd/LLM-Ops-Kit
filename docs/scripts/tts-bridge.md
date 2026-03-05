# tts-bridge

**Created**: 2026-03-03
**Updated**: 2026-03-03

Run a local OpenAI-compatible TTS bridge that forwards to your MLX Audio server and injects a configured voice clone payload (`model`, `voice`, `ref_audio`, `ref_text`).

```bash
~/bin/tts-bridge [start|stop|restart|status]
```

Default runtime:

- Listen: `127.0.0.1:11440`
- Upstream MLX: `http://127.0.0.1:11439/v1`

Port note:

- `11440` (bridge) and `11439` (upstream MLX) are defaults, not requirements.
- Any free/open ports will work.
- If you change ports, keep `TTS_BRIDGE_UPSTREAM_BASE` and OpenClaw `messages.tts.openai.baseUrl` in sync.

Default voice clone sample:

- `TTS_BRIDGE_REF_AUDIO=$HOME/LLM_Repository/TTS/Samples/Mia-Faith-Prof-Emotive-60s-Sample-Mastered-01.wav`
- `TTS_BRIDGE_REF_TEXT=$HOME/LLM_Repository/TTS/Samples/Mia-Faith-Prof-Emotive-60s-Sample-Mastered-01.txt`

Environment overrides:

- `TTS_BRIDGE_HOST`
- `TTS_BRIDGE_PORT`
- `TTS_BRIDGE_UPSTREAM_BASE`
- `TTS_BRIDGE_MODEL`
- `TTS_BRIDGE_VOICE`
- `TTS_BRIDGE_REF_AUDIO`
- `TTS_BRIDGE_REF_TEXT`
- `TTS_BRIDGE_PYTHON_BIN`

OpenClaw wiring:

```bash
export OPENAI_TTS_BASE_URL=http://127.0.0.1:11440/v1
```

Then set `messages.tts.provider` to `openai` in `~/.openclaw/openclaw.json`.
