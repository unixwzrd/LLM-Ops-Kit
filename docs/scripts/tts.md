# tts

**Created**: 2026-03-01
**Updated**: 2026-03-01

Run/control local MLX Audio TTS server (`mlx_audio.server`) via model profile `Qwen3TTS`.

```bash
~/bin/tts [start|stop|restart|status]
~/bin/Qwen3TTS [start|stop|restart|status|settings]
```

Examples:

```bash
~/bin/tts start
~/bin/tts status
~/bin/Qwen3TTS settings
```

Qwen3-TTS smoke test:

```bash
curl -sS http://127.0.0.1:18081/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "'"$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"'",
    "input": "Hello from local MLX TTS.",
    "response_format": "wav"
  }' \
  --output /tmp/tts-test.wav
```

Optional env overrides:

- `OPENCLAW_TTS_HOST` (default `127.0.0.1`)
- `OPENCLAW_TTS_PORT` (default `18081`)
- `OPENCLAW_TTS_PYTHON` (default `python3`)
- `OPENCLAW_TTS_MODULE` (default `mlx_audio.server`)

Notes:

- `~/bin/tts` is a convenience alias for `modelctl Qwen3TTS`.
- Server runtime behavior is managed by `scripts/models/Qwen3TTS.sh` and `scripts/defaults/tts-defaults.sh`.
