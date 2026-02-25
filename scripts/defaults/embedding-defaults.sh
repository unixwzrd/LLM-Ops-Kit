# shellcheck shell=bash
# Embedding-kind defaults (applied after model profile; only fill missing values).
MODEL_KIND="${MODEL_KIND:-embedding}"
CTX_SIZE="${CTX_SIZE:-1024}"
GPU_LAYERS="${GPU_LAYERS:-99}"
BATCH_SIZE="${BATCH_SIZE:-1024}"
UBATCH_SIZE="${UBATCH_SIZE:-512}"
POOLING="${POOLING:-mean}"
USE_NO_MMAP="${USE_NO_MMAP:-0}"
