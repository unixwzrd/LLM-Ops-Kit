# shellcheck shell=bash
# Model-specific defaults for Qwen3 (applied before model-kind defaults).
# Fill only when still unset so external env can override.
# Identity/profile
MODEL_TYPE="${MODEL_TYPE:-llm}"

# Model artifacts
MODEL="${MODEL:-$HOME/LLM_Repository/Qwen3-VL-32B-Gemini-Heretic-Uncensored-Thinking-GGUF/Qwen3-VL-32B-Gemini-Heretic-Uncensored-Thinking.Q8_0.gguf}"
MMPROJ="${MMPROJ:-$HOME/LLM_Repository/Qwen3-VL-32B-Gemini-Heretic-Uncensored-Thinking-GGUF/Qwen3-VL-32B-Gemini-Heretic-Uncensored-Thinking.mmproj-Q8_0.gguf}"
PORT="${PORT:-11434}"

# Runtime/network
HOST="${HOST:-0.0.0.0}"
THREADS="${THREADS:-$(default_threads)}"
THREADS_BATCH="${THREADS_BATCH:-$THREADS}"

# llama.cpp sizing (Qwen-tuned)
CTX_SIZE="${CTX_SIZE:-49152}"
GPU_LAYERS="${GPU_LAYERS:-99}"
BATCH_SIZE="${BATCH_SIZE:-768}"
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

# Sampling defaults (external env or ~/.llm-ops/config.env can override directly)
TEMP="${TEMP:-1.0}"
TOP_P="${TOP_P:-0.95}"
TOP_K="${TOP_K:-20}"
MIN_P="${MIN_P:-0.0}"
PRESENCE_PENALTY="${PRESENCE_PENALTY:-1.5}"
REPEAT_PENALTY="${REPEAT_PENALTY:-1.0}"
