# shellcheck shell=bash
# Model-specific defaults for Qwen3
MODEL_PROFILE="Qwen3VL"
MODEL_KIND="llm"
MODEL="${MODEL:-$HOME/LLM_Repository/Qwen3-VL-32B-Gemini-Heretic-Uncensored-Thinking-GGUF/Qwen3-VL-32B-Gemini-Heretic-Uncensored-Thinking.Q8_0.gguf}"
MMPROJ="${MMPROJ:-$HOME/LLM_Repository/Qwen3-VL-32B-Gemini-Heretic-Uncensored-Thinking-GGUF/Qwen3-VL-32B-Gemini-Heretic-Uncensored-Thinking.mmproj-Q8_0.gguf}"
PORT="${PORT:-11434}"

# Qwen3VL runtime defaults
THREADS_BATCH="${THREADS_BATCH:-$THREADS}"
USE_MLOCK="${USE_MLOCK:-1}"
USE_NO_MMAP="${USE_NO_MMAP:-1}"
USE_NO_WEBUI="${USE_NO_WEBUI:-1}"
