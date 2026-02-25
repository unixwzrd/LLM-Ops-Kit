# shellcheck shell=bash
# LLM-kind defaults (template-style; fill only when still unset).

# Identity/profile
MODEL_KIND="${MODEL_KIND:-llm}"
MODEL_PROFILE="${MODEL_PROFILE:-llm-generic}"

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

# Runtime feature flags
USE_MLOCK="${USE_MLOCK:-1}"
USE_NO_MMAP="${USE_NO_MMAP:-1}"
USE_NO_WEBUI="${USE_NO_WEBUI:-1}"

# Prompt/template settings
USE_CUSTOM_TEMPLATE="${USE_CUSTOM_TEMPLATE:-0}"
CHAT_TEMPLATE="${CHAT_TEMPLATE:-}"
VERBOSE_PROMPT="${VERBOSE_PROMPT:-0}"
