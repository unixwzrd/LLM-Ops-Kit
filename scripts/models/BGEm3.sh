# shellcheck shell=bash
# Model-specific defaults for BGEm3 (applied before model-kind defaults).
# Fill only when still unset so external env can override.

# Identity/profile
MODEL_TYPE="${MODEL_TYPE:-embedding}"

# Model artifacts
MODEL="${MODEL:-$HOME/LLM_Repository/bge-m3-Q8_0-GGUF/bge-m3-q8_0.gguf}"
PORT="${PORT:-11435}"

# Runtime/network
HOST="${HOST:-0.0.0.0}"
THREADS="${THREADS:-$(default_threads)}"
THREADS_BATCH="${THREADS_BATCH:-$THREADS}"

# llama.cpp sizing (BGE-tuned)
CTX_SIZE="${CTX_SIZE:-8192}"
GPU_LAYERS="${GPU_LAYERS:-99}"
BATCH_SIZE="${BATCH_SIZE:-3072}"
UBATCH_SIZE="${UBATCH_SIZE:-3072}"
CACHE_TYPE_K="${CACHE_TYPE_K:-}"
CACHE_TYPE_V="${CACHE_TYPE_V:-}"

# Embedding-specific
POOLING="${POOLING:-mean}"
USE_NO_MMAP="${USE_NO_MMAP:-0}"
USE_NO_WEBUI="${USE_NO_WEBUI:-1}"

# Prompt/template settings (typically unused for embeddings)
USE_CUSTOM_TEMPLATE="${USE_CUSTOM_TEMPLATE:-0}"
CHAT_TEMPLATE="${CHAT_TEMPLATE:-}"
VERBOSE_PROMPT="${VERBOSE_PROMPT:-0}"
