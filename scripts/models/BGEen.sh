# shellcheck shell=bash
# Model-specific defaults for BGEen (applied before model-kind defaults).
# Fill only when still unset so external env can override.

# Identity/profile
MODEL_TYPE="${MODEL_TYPE:-embedding}"
MODEL_PROFILE="${MODEL_PROFILE:-bge-small-en}"

# Model artifacts
MODEL="${MODEL:-$HOME/LLM_Repository/bge-small-en-v1.5-Q8_0-GGUF/bge-small-en-v1.5-q8_0.gguf}"
PORT="${PORT:-11435}"

# Runtime/network
HOST="${HOST:-0.0.0.0}"
THREADS="${THREADS:-$(default_threads)}"
THREADS_BATCH="${THREADS_BATCH:-$THREADS}"

# llama.cpp sizing (BGE-tuned)
# bge-small-en-v1.5 is effectively 512-token context.
CTX_SIZE="${CTX_SIZE:-512}"
GPU_LAYERS="${GPU_LAYERS:-99}"
BATCH_SIZE="${BATCH_SIZE:-1024}"
UBATCH_SIZE="${UBATCH_SIZE:-1024}"

# Embedding-specific
POOLING="${POOLING:-mean}"
USE_NO_MMAP="${USE_NO_MMAP:-0}"
USE_NO_WEBUI="${USE_NO_WEBUI:-1}"

# Prompt/template settings (typically unused for embeddings)
USE_CUSTOM_TEMPLATE="${USE_CUSTOM_TEMPLATE:-0}"
CHAT_TEMPLATE="${CHAT_TEMPLATE:-}"
VERBOSE_PROMPT="${VERBOSE_PROMPT:-0}"
