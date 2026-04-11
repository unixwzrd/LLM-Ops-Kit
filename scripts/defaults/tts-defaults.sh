# shellcheck shell=bash
# TTS-kind defaults (template-style; fill only when still unset).

# Identity/profile
MODEL_TYPE="${MODEL_TYPE:-tts}"

# TTS model reference (path or model id used by clients)
MODEL="${MODEL:-}"

# Runtime/network
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-18081}"

# TTS server runtime
TTS_PYTHON_BIN="${TTS_PYTHON_BIN:-python}"
TTS_SERVER_MODULE="${TTS_SERVER_MODULE:-mlx_audio.server}"
TTS_API_KEY="${TTS_API_KEY:-}"

# Optional passthrough arg string for server invocation (advanced use)
TTS_SERVER_ARGS="${TTS_SERVER_ARGS:-}"
