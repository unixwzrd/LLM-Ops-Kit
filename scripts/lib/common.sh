#! /usr/bin/env bash
set -euo pipefail

LLMOPS_HOME="${LLMOPS_HOME:-$HOME/.llm-ops}"
LLMOPS_RUN_DIR="${LLMOPS_RUN_DIR:-$LLMOPS_HOME/run}"
LLMOPS_LOG_DIR="${LLMOPS_LOG_DIR:-$LLMOPS_HOME/logs}"
LLMOPS_ROOT="${LLMOPS_ROOT:-$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)}"

ensure_runtime_dirs() {
  mkdir -p "$LLMOPS_RUN_DIR" "$LLMOPS_LOG_DIR"
}

load_shell_env() {
  # Do not source interactive shell init files here; they may contain
  # framework hooks (venv managers, prompt tooling) that break non-interactive
  # service wrappers. Load only explicit env files.
  local files=()
  if [[ -n "${LLMOPS_ENV_FILE:-}" ]]; then
    files+=("$LLMOPS_ENV_FILE")
  fi
  # Base user env first, then repo defaults, then runtime-local overrides last.
  # This lets ~/.llm-ops/config.env force service-specific settings without
  # editing the shared ~/.env file.
  files+=("$HOME/.env")
  files+=("$LLMOPS_ROOT/config/hosts.env" "$LLMOPS_ROOT/config/hosts.local.env")
  files+=("$LLMOPS_HOME/config.env" "$LLMOPS_HOME/hosts.env")
  local f
  for f in "${files[@]}"; do
    if [[ -f "$f" ]]; then
      # shellcheck disable=SC1090
      . "$f"
    fi
  done
}

cpu_count() {
  local n=""

  if [[ -n "${LLMOPS_CPU_COUNT_OVERRIDE:-}" ]]; then
    n="$LLMOPS_CPU_COUNT_OVERRIDE"
  elif command -v getconf >/dev/null 2>&1; then
    n="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
  elif command -v nproc >/dev/null 2>&1; then
    n="$(nproc 2>/dev/null || true)"
  elif command -v sysctl >/dev/null 2>&1; then
    n="$(sysctl -n hw.logicalcpu 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || true)"
  fi

  if [[ -z "$n" || ! "$n" =~ ^[0-9]+$ || "$n" -lt 1 ]]; then
    n=4
  fi
  printf '%s\n' "$n"
}

default_threads() {
  local n t
  n="$(cpu_count)"
  t=$((n * 2))
  if [[ "$t" -lt 1 ]]; then
    t=1
  fi
  printf '%s\n' "$t"
}

pid_file_for() {
  local name="$1"
  printf '%s/%s.pid\n' "$LLMOPS_RUN_DIR" "$name"
}

is_pid_running() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

read_pid() {
  local name="$1"
  local pf
  pf="$(pid_file_for "$name")"
  [[ -f "$pf" ]] || return 1
  cat "$pf"
}

write_pid() {
  local name="$1"
  local pid="$2"
  local pf
  pf="$(pid_file_for "$name")"
  printf '%s\n' "$pid" > "$pf"
}

stop_by_name() {
  local name="$1"
  local pf pid
  pf="$(pid_file_for "$name")"
  if [[ ! -f "$pf" ]]; then
    echo "$name: no pid file"
    return 0
  fi
  pid="$(cat "$pf")"
  if is_pid_running "$pid"; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if is_pid_running "$pid"; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "$name: stopped pid $pid"
  else
    echo "$name: stale pid file ($pid)"
  fi
  rm -f "$pf"
}
