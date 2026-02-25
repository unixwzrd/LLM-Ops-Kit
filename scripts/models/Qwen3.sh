# shellcheck shell=bash
# Model-specific defaults for Qwen3 (applied before model-kind defaults).
# Fill only when still unset so external env can override.

# Identity/profile
MODEL_KIND="${MODEL_KIND:-llm}"
MODEL_PROFILE="${MODEL_PROFILE:-Qwen3VL}"

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

# Runtime feature flags (Qwen-tuned)
USE_MLOCK="${USE_MLOCK:-1}"
USE_NO_MMAP="${USE_NO_MMAP:-1}"
USE_NO_WEBUI="${USE_NO_WEBUI:-1}"

# Prompt/template settings (Qwen-tuned)
USE_CUSTOM_TEMPLATE="${USE_CUSTOM_TEMPLATE:-1}"
CHAT_TEMPLATE="${CHAT_TEMPLATE:-/Users/miafour/projects/agent-work/scripts/templates/chatml-tools.jinja}"
VERBOSE_PROMPT="${VERBOSE_PROMPT:-0}"
