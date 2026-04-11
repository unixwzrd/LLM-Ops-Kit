# shellcheck shell=bash
# LLM-kind defaults (template-style; fill only when still unset).
# Precedence is handled by modelctl load order:
# external env -> model profile -> these model-kind defaults -> llama defaults.

# Identity/profile
MODEL_TYPE="${MODEL_TYPE:-llm}"

# Model artifacts
MODEL="${MODEL:-}"
MMPROJ="${MMPROJ:-}"
PORT="${PORT:-11434}"

# Runtime/network
HOST="${HOST:-0.0.0.0}"
THREADS="${THREADS:-$(default_threads)}"
THREADS_BATCH="${THREADS_BATCH:-$THREADS}"

# llama.cpp sizing
CTX_SIZE="${CTX_SIZE:-32768}"
GPU_LAYERS="${GPU_LAYERS:-99}"
BATCH_SIZE="${BATCH_SIZE:-512}"
UBATCH_SIZE="${UBATCH_SIZE:-512}"
CACHE_TYPE_K="${CACHE_TYPE_K:-}"
CACHE_TYPE_V="${CACHE_TYPE_V:-}"

# Runtime feature flags
USE_MLOCK="${USE_MLOCK:-1}"
USE_NO_MMAP="${USE_NO_MMAP:-1}"
DIRECT_IO="${DIRECT_IO:-0}"
USE_NO_WEBUI="${USE_NO_WEBUI:-1}"

# Prompt/template settings
USE_CUSTOM_TEMPLATE="${USE_CUSTOM_TEMPLATE:-0}"
CHAT_TEMPLATE="${CHAT_TEMPLATE:-}"
VERBOSE_PROMPT="${VERBOSE_PROMPT:-0}"

# Generic sampling defaults for LLMs (model profiles may override)
TEMP="${TEMP:-}"
TOP_P="${TOP_P:-}"
TOP_K="${TOP_K:-}"
MIN_P="${MIN_P:-}"
PRESENCE_PENALTY="${PRESENCE_PENALTY:-}"
REPEAT_PENALTY="${REPEAT_PENALTY:-}"

# Optional generic knobs for model profiles
LLM_TEMPLATE_MODE="${LLM_TEMPLATE_MODE:-stable}"
LLM_PRESET="${LLM_PRESET:-default}"
