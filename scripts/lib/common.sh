#! /usr/bin/env bash
set -euo pipefail

llmops_default_config_home() {
  if [[ -n "${LLMOPS_CONFIG_HOME:-}" ]]; then
    printf '%s\n' "$LLMOPS_CONFIG_HOME"
  elif [[ -f "${LLMOPS_HOME:-$HOME/.local/llm-ops}/current/config/config.json" ]]; then
    printf '%s/current/config\n' "${LLMOPS_HOME:-$HOME/.local/llm-ops}"
  elif [[ -n "${XDG_CONFIG_HOME:-}" ]]; then
    printf '%s/llm-ops\n' "$XDG_CONFIG_HOME"
  else
    printf '%s/.config/llm-ops\n' "$HOME"
  fi
}

llmops_default_state_home() {
  if [[ -n "${LLMOPS_STATE_HOME:-}" ]]; then
    printf '%s\n' "$LLMOPS_STATE_HOME"
  elif [[ -n "${XDG_STATE_HOME:-}" ]]; then
    printf '%s/llm-ops\n' "$XDG_STATE_HOME"
  else
    printf '%s/.local/state/llm-ops\n' "$HOME"
  fi
}

LLMOPS_HOME="${LLMOPS_HOME:-$HOME/.local/llm-ops}"
LLMOPS_CONFIG_HOME="${LLMOPS_CONFIG_HOME:-$(llmops_default_config_home)}"
LLMOPS_STATE_HOME="${LLMOPS_STATE_HOME:-$(llmops_default_state_home)}"
LLMOPS_RUN_DIR="${LLMOPS_RUN_DIR:-$LLMOPS_STATE_HOME/run}"
LLMOPS_LOG_DIR="${LLMOPS_LOG_DIR:-$LLMOPS_STATE_HOME/logs}"
LLMOPS_ROOT="${LLMOPS_ROOT:-$(cd -P "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd)}"
LLMOPS_CONFIG_DIR="${LLMOPS_CONFIG_DIR:-$LLMOPS_CONFIG_HOME/config}"
LLMOPS_BACKUP_DIR="${LLMOPS_BACKUP_DIR:-$LLMOPS_STATE_HOME/backups}"

LLMOPS_LOG_ROTATE_BYTES="${LLMOPS_LOG_ROTATE_BYTES:-10485760}"
LLMOPS_LOG_ROTATE_KEEP="${LLMOPS_LOG_ROTATE_KEEP:-5}"
LLMOPS_LOG_ROTATE_MAX_AGE_DAYS="${LLMOPS_LOG_ROTATE_MAX_AGE_DAYS:-14}"
LLMOPS_BACKUP_KEEP="${LLMOPS_BACKUP_KEEP:-5}"
LLMOPS_BACKUP_MAX_AGE_DAYS="${LLMOPS_BACKUP_MAX_AGE_DAYS:-30}"

LLMOPS_LOG_MARKTIME_ENABLED="${LLMOPS_LOG_MARKTIME_ENABLED:-1}"
LLMOPS_LOG_MARKTIME_INTERVAL_SECONDS="${LLMOPS_LOG_MARKTIME_INTERVAL_SECONDS:-300}"
LLMOPS_LOG_MARKTIME_FORMAT="${LLMOPS_LOG_MARKTIME_FORMAT:-+%Y-%m-%d %H:%M:%S UTC}"

ensure_runtime_dirs() {
  mkdir -p "$LLMOPS_RUN_DIR" "$LLMOPS_LOG_DIR" "$LLMOPS_BACKUP_DIR" "$LLMOPS_CONFIG_DIR"
}

state_file_path() {
  printf '%s\n' "${LLMOPS_STATE_FILE:-$LLMOPS_STATE_HOME/runtime-state.env}"
}

prepend_path_once() {
  local dir="$1"
  [[ -d "$dir" ]] || return 0
  case ":${PATH:-}:" in
    *":$dir:"*) ;;
    *) PATH="$dir${PATH:+:$PATH}" ;;
  esac
  export PATH
}

runtime_venv_path() {
  local state_file venv
  if [[ -n "${LLMOPS_RUNTIME_VENV_PATH:-}" ]]; then
    printf '%s\n' "$LLMOPS_RUNTIME_VENV_PATH"
    return 0
  fi
  state_file="$(state_file_path)"
  if [[ -f "$state_file" ]]; then
    venv="$(sed -n 's/^LLMOPS_RUNTIME_VENV_PATH=//p' "$state_file" | tail -n 1)"
    if [[ -n "$venv" ]]; then
      printf '%s\n' "$venv"
      return 0
    fi
  fi
  return 1
}

maybe_prepend_runtime_venv_bin() {
  local venv=""
  venv="$(runtime_venv_path 2>/dev/null || true)"
  [[ -n "$venv" ]] || return 0
  prepend_path_once "$venv/bin"
}

load_shell_env() {
  # Runtime configuration comes from canonical JSON. An explicit environment
  # file is accepted only as a secret-injection boundary.
  local f="${LLMOPS_ENV_FILE:-}"
  if [[ -n "${LLMOPS_ENV_FILE:-}" ]]; then
    [[ -f "$f" ]] || {
      echo "llmops: explicit secret environment file not found: $f" >&2
      return 2
    }
    set -a
    # shellcheck disable=SC1090
    . "$f"
    set +a
    strip_self_placeholder_env_values
  fi
  maybe_prepend_runtime_venv_bin
}

llmops_config_home() {
  printf '%s\n' "$LLMOPS_CONFIG_HOME"
}

llmops_service_profile_path() {
  local service="$1"
  printf '%s/services/%s.json\n' "$(llmops_config_home)" "$service"
}

llmops_model_profile_path() {
  local model="$1"
  printf '%s/models/%s.json\n' "$(llmops_config_home)" "$model"
}

llmops_agent_profile_path() {
  local backend="$1"
  printf '%s/agents/%s.json\n' "$(llmops_config_home)" "$backend"
}

source_json_profile_defaults() {
  local kind="$1"
  local name="$2"
  local json_file="$3"
  local line key resolved
  [[ -f "$json_file" ]] || return 0
  resolved="$("${LLMOPS_PYTHON_BIN:-python3}" "$LLMOPS_ROOT/scripts/lib/llmops_profiles.py" "$kind" "$name" --profile-path "$json_file" --resolve-references)" || return $?
  while IFS= read -r line; do
    [[ -n "$line" && "$line" == *=* ]] || continue
    key="${line%%=*}"
    if [[ -z "${!key-}" ]]; then
      eval "export $line"
    fi
  done <<< "$resolved"
}

source_json_model_profile_defaults() {
  local model="$1"
  local json_file="${2:-$(llmops_model_profile_path "$model")}"
  source_json_profile_defaults model "$model" "$json_file"
}

source_json_agent_profile_defaults() {
  local backend="$1"
  local json_file="${2:-$(llmops_agent_profile_path "$backend")}"
  source_json_profile_defaults agent "$backend" "$json_file"
}

source_json_service_profile_defaults() {
  local service="$1"
  local json_file="${2:-$(llmops_service_profile_path "$service")}"
  source_json_profile_defaults service "$service" "$json_file"
}

strip_self_placeholder_env_values() {
  local name value
  while IFS='=' read -r name _; do
    [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${!name-}"
    case "$value" in
      "\${$name}"|"\$$name")
        unset "$name" || true
        ;;
    esac
  done < <(env)
}

runtime_mode() {
  local state_file mode
  state_file="$(state_file_path)"
  mode="${LLMOPS_RUNTIME_MODE:-}"
  if [[ -n "$mode" ]]; then
    printf '%s\n' "$mode"
    return 0
  fi
  if [[ -f "$state_file" ]]; then
    mode="$(sed -n 's/^LLMOPS_INSTALL_MODE=//p' "$state_file" | tail -n 1)"
  fi
  printf '%s\n' "${mode:-installed}"
}

runtime_asset_root() {
  printf '%s\n' "$LLMOPS_ROOT"
}

file_size_bytes() {
  local path="$1"
  [[ -f "$path" ]] || { printf '0\n'; return 0; }
  wc -c < "$path" | tr -d '[:space:]'
}

rotate_log_if_needed() {
  local log_file="$1"
  local max_bytes size stamp rotated
  max_bytes="${2:-$LLMOPS_LOG_ROTATE_BYTES}"
  [[ -n "$log_file" ]] || return 0
  [[ -f "$log_file" ]] || return 0
  [[ "$max_bytes" =~ ^[0-9]+$ ]] || return 0
  (( max_bytes > 0 )) || return 0

  size="$(file_size_bytes "$log_file")"
  [[ "$size" =~ ^[0-9]+$ ]] || size=0
  (( size < max_bytes )) && return 0

  stamp="$(date +%Y%m%d-%H%M%S)"
  rotated="${log_file}.${stamp}"
  mv "$log_file" "$rotated"
}

prune_rotated_logs() {
  local log_file="$1"
  local keep="${2:-$LLMOPS_LOG_ROTATE_KEEP}"
  local max_age_days="${3:-$LLMOPS_LOG_ROTATE_MAX_AGE_DAYS}"
  local dir base count=0
  local -a rotated=()

  [[ -n "$log_file" ]] || return 0
  dir="$(dirname "$log_file")"
  base="$(basename "$log_file")"
  [[ -d "$dir" ]] || return 0

  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    rotated+=("$path")
  done < <(find "$dir" -maxdepth 1 -type f -name "${base}.*" | sort -r)

  if [[ "$max_age_days" =~ ^[0-9]+$ ]] && (( max_age_days > 0 )); then
    find "$dir" -maxdepth 1 -type f -name "${base}.*" -mtime +"$max_age_days" -exec rm -f {} +
    rotated=()
    while IFS= read -r path; do
      [[ -n "$path" ]] || continue
      rotated+=("$path")
    done < <(find "$dir" -maxdepth 1 -type f -name "${base}.*" | sort -r)
  fi

  if [[ "$keep" =~ ^[0-9]+$ ]] && (( keep >= 0 )); then
    for path in "${rotated[@]-}"; do
      [[ -n "$path" ]] || continue
      count=$((count + 1))
      if (( count > keep )); then
        rm -f "$path"
      fi
    done
  fi
}

prepare_log_file() {
  local log_file="$1"
  ensure_runtime_dirs
  rotate_log_if_needed "$log_file"
  prune_rotated_logs "$log_file"
  touch "$log_file"
}

archive_log_for_restart() {
  local log_file="$1"
  local stamp rotated
  [[ -s "$log_file" ]] || return 0
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  rotated="${log_file}.${stamp}"
  if [[ -e "$rotated" ]]; then
    rotated="${rotated}.$$"
  fi
  mv "$log_file" "$rotated"
  prune_rotated_logs "$log_file"
}

prune_runtime_backups() {
  local keep="${1:-$LLMOPS_BACKUP_KEEP}"
  local max_age_days="${2:-$LLMOPS_BACKUP_MAX_AGE_DAYS}"
  local count=0 path
  local -a backups=()

  [[ -d "$LLMOPS_BACKUP_DIR" ]] || return 0

  if [[ "$max_age_days" =~ ^[0-9]+$ ]] && (( max_age_days > 0 )); then
    find "$LLMOPS_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$max_age_days" -exec rm -rf {} +
  fi

  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    backups+=("$path")
  done < <(find "$LLMOPS_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d | sort -r)

  if [[ "$keep" =~ ^[0-9]+$ ]] && (( keep >= 0 )); then
    for path in "${backups[@]-}"; do
      [[ -n "$path" ]] || continue
      count=$((count + 1))
      if (( count > keep )); then
        rm -rf "$path"
      fi
    done
  fi
}

prune_runtime_artifacts() {
  ensure_runtime_dirs
  prune_runtime_backups "$LLMOPS_BACKUP_KEEP" "$LLMOPS_BACKUP_MAX_AGE_DAYS"
}

retention_summary_line() {
  printf 'logs rotate=%s keep=%s age_days=%s backups keep=%s age_days=%s\n' \
    "$LLMOPS_LOG_ROTATE_BYTES" \
    "$LLMOPS_LOG_ROTATE_KEEP" \
    "$LLMOPS_LOG_ROTATE_MAX_AGE_DAYS" \
    "$LLMOPS_BACKUP_KEEP" \
    "$LLMOPS_BACKUP_MAX_AGE_DAYS"
}

dir_usage_bytes() {
  local path="$1"
  [[ -d "$path" ]] || { printf '0\n'; return 0; }
  du -sk "$path" 2>/dev/null | awk '{print $1 * 1024}'
}

print_missing_config_hint() {
  local message="$1"
  shift || true
  local var
  echo "$message" >&2
  echo "Set the value in the canonical JSON profile or inject it explicitly." >&2
  echo "Example:" >&2
  for var in "$@"; do
    case "$var" in
      LLMOPS_UPSTREAM_HOST|LLMOPS_SYNC_HOST)
        echo "  export $var=<example-upstream-host>" >&2
        ;;
      LLMOPS_UPSTREAM_PORT|MODEL_PROXY_LISTEN_PORT|TTS_BRIDGE_PORT)
        echo "  export $var=<port>" >&2
        ;;
      TTS_BRIDGE_UPSTREAM_BASE)
        echo "  export $var=http://<example-upstream-host>:<port>/v1" >&2
        ;;
      MODEL_PROXY_LISTEN_HOST|TTS_BRIDGE_HOST)
        echo "  export $var=127.0.0.1" >&2
        ;;
      *)
        echo "  export $var=<value>" >&2
        ;;
    esac
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


marktime_pid_name() {
  local name="$1"
  printf '%s-marktime\n' "$name"
}

stop_log_marktime() {
  local name="$1"
  local marker_name pf pid
  marker_name="$(marktime_pid_name "$name")"
  pf="$(pid_file_for "$marker_name")"
  [[ -f "$pf" ]] || return 0
  pid="$(cat "$pf")"
  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if is_pid_running "$pid"; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "$pf"
}

start_log_marktime() {
  local name="$1"
  local label="$2"
  local log_file="$3"
  local marker_name pf pid interval format

  [[ "${LLMOPS_LOG_MARKTIME_ENABLED:-1}" == "1" ]] || return 0
  [[ -n "$log_file" ]] || return 0

  interval="${LLMOPS_LOG_MARKTIME_INTERVAL_SECONDS:-300}"
  [[ "$interval" =~ ^[0-9]+$ ]] || return 0
  (( interval > 0 )) || return 0

  format="${LLMOPS_LOG_MARKTIME_FORMAT:-+%Y-%m-%d %H:%M:%S UTC}"
  marker_name="$(marktime_pid_name "$name")"
  pf="$(pid_file_for "$marker_name")"

  if [[ -f "$pf" ]]; then
    pid="$(cat "$pf")"
    if [[ -n "$pid" ]] && is_pid_running "$pid"; then
      return 0
    fi
    rm -f "$pf"
  fi

  # shellcheck disable=SC2016
  nohup bash -c '
      label="$1"
      log_file="$2"
      format="$3"
      interval="$4"
      while :; do
        printf "\n========== %s - MARKTIME  %s ==========\n" \
          "$label" \
          "$(date -u "$format")" >> "$log_file"
        sleep "$interval" || exit 0
      done
    ' _ "$label" "$log_file" "$format" "$interval" \
    < /dev/null >/dev/null 2>&1 &

  write_pid "$marker_name" "$!"
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
