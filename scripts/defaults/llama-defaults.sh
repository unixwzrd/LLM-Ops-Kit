# shellcheck shell=bash
# Global llama.cpp defaults shared by all model kinds.
HOST="${HOST:-0.0.0.0}"
THREADS="${THREADS:-$(default_threads)}"
THREADS_BATCH="${THREADS_BATCH:-$THREADS}"
USE_NO_WEBUI="${USE_NO_WEBUI:-1}"
VERBOSE_PROMPT="${VERBOSE_PROMPT:-0}"
