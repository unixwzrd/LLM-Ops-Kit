# shellcheck shell=bash
# Model-specific defaults for Qwen3 TTS (applied before model-type defaults).
# Fill only when still unset so external env can override.

# Identity/profile
MODEL_TYPE="${MODEL_TYPE:-tts}"

# Canonical model location (used by clients for /v1/audio/speech "model" value)
MODEL="${MODEL:-$HOME/LLM_Repository/TTS/Qwen3-TTS-12Hz-0.6B-Base-8bit}"

# Runtime/network
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-11439}"

# TTS server runtime
TTS_PYTHON_BIN="${TTS_PYTHON_BIN:-python}"
TTS_SERVER_MODULE="${TTS_SERVER_MODULE:-mlx_audio.server}"
TTS_API_KEY="${TTS_API_KEY:-}"
TTS_SERVER_ARGS="${TTS_SERVER_ARGS:-}"
