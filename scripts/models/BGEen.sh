# shellcheck shell=bash
# Model-specific defaults for BGEen (applied before model-kind defaults).
MODEL_PROFILE="${MODEL_PROFILE:-bge-small-en}"
MODEL_KIND="${MODEL_KIND:-embedding}"
MODEL="${MODEL:-$HOME/LLM_Repository/bge-small-en-v1.5-Q8_0-GGUF/bge-small-en-v1.5-q8_0.gguf}"
PORT="${PORT:-11435}"

# BGE-tuned defaults; external env still wins.
CTX_SIZE="${CTX_SIZE:-1024}"
GPU_LAYERS="${GPU_LAYERS:-99}"
BATCH_SIZE="${BATCH_SIZE:-1024}"
UBATCH_SIZE="${UBATCH_SIZE:-512}"
POOLING="${POOLING:-mean}"
USE_NO_WEBUI="${USE_NO_WEBUI:-1}"
