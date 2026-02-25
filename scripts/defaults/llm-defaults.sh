# shellcheck shell=bash
# LLM-kind defaults (applied after model profile; only fill missing values).
MODEL_KIND="${MODEL_KIND:-llm}"
CTX_SIZE="${CTX_SIZE:-32768}"
GPU_LAYERS="${GPU_LAYERS:-99}"
BATCH_SIZE="${BATCH_SIZE:-512}"
UBATCH_SIZE="${UBATCH_SIZE:-512}"
USE_MLOCK="${USE_MLOCK:-1}"
USE_NO_MMAP="${USE_NO_MMAP:-1}"
