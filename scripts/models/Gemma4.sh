# shellcheck shell=bash
# Model-specific defaults for Qwen3.5 (applied before model-kind defaults).
# Fill only when still unset so external env can override.
# Identity/profile
MODEL_TYPE="${MODEL_TYPE:-llm}"
MODEL_PROFILE="${MODEL_PROFILE:-Qwen3_5}"

# Model artifacts
MODEL="${MODEL:-$HOME/LLM_Repository/gemma-4-31B-it-GGUF/gemma-4-31B-it-UD-Q8_K_XL.gguf}"
MMPROJ="${MMPROJ:-$HOME/LLM_Repository/gemma-4-31B-it-GGUF/mmproj-BF16.gguf}"
PORT="${PORT:-11434}"

# Runtime/network
HOST="${HOST:-0.0.0.0}"
THREADS="${THREADS:-$(default_threads)}"
THREADS_BATCH="${THREADS_BATCH:-$THREADS}"

# llama.cpp sizing (Qwen3.5-tuned defaults)
CTX_SIZE="${CTX_SIZE:-32768}"
GPU_LAYERS="${GPU_LAYERS:-99}"
BATCH_SIZE="${BATCH_SIZE:-1024}"
UBATCH_SIZE="${UBATCH_SIZE:-512}"

# Runtime feature flags
USE_MLOCK="${USE_MLOCK:-1}"
USE_NO_MMAP="${USE_NO_MMAP:-1}"
DIRECT_IO="${DIRECT_IO:-1}"
# DISABLE_TOOL_GRAMMAR="${DISABLE_TOOL_GRAMMAR:-1}"

USE_NO_WEBUI="${USE_NO_WEBUI:-1}"

# Prompt/template settings
#VERBOSE_PROMPT="${VERBOSE_PROMPT:-1}"
VERBOSE_PROMPT="${VERBOSE_PROMPT:-0}"
USE_CUSTOM_TEMPLATE="${USE_CUSTOM_TEMPLATE:-0}"
# CHAT_TEMPLATE="${CHAT_TEMPLATE:-$HOME/.llm-ops/current/scripts/templates/Qwen-3_5-stock-template.jinja}"

# Sampling defaults (external env or ~/.llm-ops/config.env can override directly)
TEMP="${TEMP:-1.0}"
TOP_P="${TOP_P:-0.95}"
TOP_K="${TOP_K:-64}"
MIN_P="${MIN_P:-0.0}"
PRESENCE_PENALTY="${PRESENCE_PENALTY:-1.5}"
REPEAT_PENALTY="${REPEAT_PENALTY:-1.0}"
