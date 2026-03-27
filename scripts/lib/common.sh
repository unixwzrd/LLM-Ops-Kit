#! /usr/bin/env bash
set -euo pipefail

LLMOPS_HOME="${LLMOPS_HOME:-$HOME/.llm-ops}"
LLMOPS_RUN_DIR="${LLMOPS_RUN_DIR:-$LLMOPS_HOME/run}"
LLMOPS_LOG_DIR="${LLMOPS_LOG_DIR:-$LLMOPS_HOME/logs}"
LLMOPS_ROOT="${LLMOPS_ROOT:-$(cd -P "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd)}"
LLMOPS_CONFIG_DIR="${LLMOPS_CONFIG_DIR:-$LLMOPS_HOME/config}"
LLMOPS_BACKUP_DIR="${LLMOPS_BACKUP_DIR:-$LLMOPS_HOME/backups}"

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

load_shell_env() {
  # Do not source interactive shell init files here; they may contain
  # framework hooks (venv managers, prompt tooling) that break non-interactive
  # service wrappers. Load only explicit env files.
  local early_files=()
  local late_files=()
  local f
  if [[ -n "${LLMOPS_ENV_FILE:-}" ]]; then
    early_files+=("$LLMOPS_ENV_FILE")
  fi
  # Load toolkit config first so we know whether Secrets-Kit is enabled before
  # touching placeholder-based ~/.env files.
  early_files+=("$LLMOPS_ROOT/config/hosts.env" "$LLMOPS_ROOT/config/hosts.local.env")
  early_files+=("$LLMOPS_HOME/config.env" "$LLMOPS_HOME/hosts.env")
  for f in "${early_files[@]}"; do
    if [[ -f "$f" ]]; then
      # shellcheck disable=SC1090
      . "$f"
    fi
  done
  maybe_load_seckit_env
  late_files+=("$HOME/.env")
  for f in "${late_files[@]}"; do
    if [[ -f "$f" ]]; then
      # The user env may now contain self-referential placeholders after
      # migration to Secrets-Kit. Source it with nounset disabled so existing
      # exported values from seckit win without tripping set -u.
      set +u
      # shellcheck disable=SC1090
      . "$f"
      set -u
    fi
  done
}

maybe_load_seckit_env() {
  local enabled bin service account export_cmd had_xtrace=0
  enabled="${LLMOPS_USE_SECKIT:-0}"
  [[ "$enabled" == "1" ]] || return 0

  bin="${LLMOPS_SECKIT_BIN:-seckit}"
  service="${LLMOPS_SECKIT_SERVICE:-openclaw}"
  account="${LLMOPS_SECKIT_ACCOUNT:-default}"

  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "warning: Secrets Kit enabled but '$bin' is not available; skipping secret export" >&2
    return 0
  fi

  if ! export_cmd="$("$bin" export --format shell --service "$service" --account "$account" --all 2>&1)"; then
    echo "warning: Secrets Kit export failed for service=$service account=$account; skipping secret export" >&2
    echo "$export_cmd" >&2
    return 0
  fi
  [[ -n "$export_cmd" ]] || return 0
  case "$-" in
    *x*)
      had_xtrace=1
      set +x
      ;;
  esac
  eval "$export_cmd"
  if [[ "$had_xtrace" == "1" ]]; then
    set -x
  fi
}

runtime_mode() {
  local state_file mode
  state_file="${LLMOPS_STATE_FILE:-$LLMOPS_HOME/runtime-state.env}"
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
    for path in "${rotated[@]}"; do
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
    for path in "${backups[@]}"; do
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

config_hint_file() {
  printf '%s/config.env\n' "$LLMOPS_HOME"
}

print_missing_config_hint() {
  local message="$1"
  shift || true
  local var
  echo "$message" >&2
  echo "Set the required value(s) in $(config_hint_file) or pass them explicitly." >&2
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
