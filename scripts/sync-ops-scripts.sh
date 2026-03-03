#!/usr/bin/env bash
set -euo pipefail

# Sync local OpenClaw-Ops-Toolkit repo to a remote host with short-lived key loading.
# Default: interactive + safe (no --delete unless requested).

HOST="${SYNC_HOST:-${OPENCLAW_UPSTREAM_HOST:-10.0.0.67}}"
USER_NAME="${SYNC_USER:-${OPENCLAW_SYNC_USER:-$USER}}"
REMOTE_DIR="${SYNC_REMOTE_DIR:-${OPENCLAW_SYNC_REMOTE_DIR:-~/projects/OpenClaw-Ops-Toolkit}}"
KEY_PATH="${SYNC_KEY_PATH:-$HOME/.ssh/id_ed25519_misfour_deploy}"
TTL="${SYNC_KEY_TTL:-20m}"
LOCAL_DIR="${SYNC_LOCAL_DIR:-$HOME/projects/OpenClaw-Ops-Toolkit/}"
DELETE_MODE=0
DRY_RUN=0
NO_AGENT=0
NO_MANIFEST=0
NO_LINKS=0
QUIET=0
STATE_FILE="${OPENCLAW_OPS_STATE_FILE:-$HOME/.openclaw-ops/runtime-state.env}"
RUNTIME_MODE="${OPENCLAW_RUNTIME_MODE:-repo}" # repo|installed
INSTALL_PREFIX="${OPENCLAW_OPS_INSTALL_BASE:-$HOME/.openclaw-ops}"
RUNTIME_MODE_EXPLICIT=0
INSTALL_PREFIX_EXPLICIT=0
ENV_RUNTIME_MODE="${OPENCLAW_RUNTIME_MODE:-}"
ENV_INSTALL_PREFIX="${OPENCLAW_OPS_INSTALL_BASE:-}"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --host <host>            Remote host (default: ${HOST})
  --user <user>            Remote user (default: ${USER_NAME})
  --remote-dir <path>      Remote destination dir (default: ${REMOTE_DIR})
  --local-dir <path>       Local source dir (default: ${LOCAL_DIR})
  --key <path>             SSH private key path (default: ${KEY_PATH})
  --ttl <duration>         ssh-add key lifetime (default: ${TTL})
  --delete                 Enable rsync --delete
  --dry-run                Enable rsync --dry-run
  --no-agent               Don't auto-start/load ssh-agent
  --no-manifest            Skip runtime-links.manifest auto-generation
  --no-links               Skip remote deploy+verify link steps after sync
  --runtime-mode <mode>    Remote runtime mode: repo (default) or installed
  --install-prefix <path>  Remote install prefix for installed mode
  --state-file <path>      Local runtime state file (default: ~/.openclaw-ops/runtime-state.env)
  --quiet                  Less output
  -h, --help               Show this help

Env overrides:
  SYNC_HOST, SYNC_USER, SYNC_REMOTE_DIR, SYNC_LOCAL_DIR, SYNC_KEY_PATH, SYNC_KEY_TTL
  OPENCLAW_UPSTREAM_HOST, OPENCLAW_SYNC_USER, OPENCLAW_SYNC_REMOTE_DIR
  OPENCLAW_RUNTIME_MODE, OPENCLAW_OPS_INSTALL_BASE, OPENCLAW_OPS_STATE_FILE
USAGE
}

log() {
  [[ "$QUIET" -eq 1 ]] && return 0
  printf '%s\n' "$*"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --user) USER_NAME="$2"; shift 2 ;;
    --remote-dir) REMOTE_DIR="$2"; shift 2 ;;
    --local-dir) LOCAL_DIR="$2"; shift 2 ;;
    --key) KEY_PATH="$2"; shift 2 ;;
    --ttl) TTL="$2"; shift 2 ;;
    --delete) DELETE_MODE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-agent) NO_AGENT=1; shift ;;
    --no-manifest) NO_MANIFEST=1; shift ;;
    --no-links) NO_LINKS=1; shift ;;
    --runtime-mode) RUNTIME_MODE="$2"; RUNTIME_MODE_EXPLICIT=1; shift 2 ;;
    --install-prefix) INSTALL_PREFIX="$2"; INSTALL_PREFIX_EXPLICIT=1; shift 2 ;;
    --state-file) STATE_FILE="$2"; shift 2 ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$RUNTIME_MODE_EXPLICIT" -eq 0 && -z "$ENV_RUNTIME_MODE" && -f "$STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  . "$STATE_FILE"
  if [[ "${OPENCLAW_OPS_INSTALL_MODE:-}" == "installed" ]]; then
    RUNTIME_MODE="installed"
  fi
  if [[ "$INSTALL_PREFIX_EXPLICIT" -eq 0 && -z "$ENV_INSTALL_PREFIX" && -n "${OPENCLAW_OPS_INSTALL_BASE:-}" ]]; then
    INSTALL_PREFIX="$OPENCLAW_OPS_INSTALL_BASE"
  fi
fi

case "$RUNTIME_MODE" in
  repo|installed) ;;
  *)
    echo "Invalid --runtime-mode: $RUNTIME_MODE (expected repo or installed)" >&2
    exit 2
    ;;
esac

[[ -d "$LOCAL_DIR" ]] || { echo "Local dir missing: $LOCAL_DIR" >&2; exit 1; }
log "Using LOCAL_DIR: $LOCAL_DIR"
log "Using REMOTE_DIR: $REMOTE_DIR"
log "Using HOST/USER: $HOST / $USER_NAME"
log "Using RUNTIME_MODE: $RUNTIME_MODE"
log "Using STATE_FILE: $STATE_FILE"

if [[ "$NO_MANIFEST" -eq 0 ]]; then
  generator="$LOCAL_DIR/scripts/generate-manifest"
  if [[ -x "$generator" ]]; then
    log "Refreshing runtime-links.manifest from launcher symlinks"
    "$generator"
  else
    log "Skipping manifest refresh (generator missing): $generator"
  fi
fi

# Preflight: ensure every manifest source exists in LOCAL_DIR before syncing.
manifest_file="$LOCAL_DIR/scripts/runtime-links.manifest"
if [[ -f "$manifest_file" ]]; then
  missing_manifest_sources=0
  while IFS='|' read -r target_rel src_rel; do
    [[ -z "${target_rel:-}" ]] && continue
    [[ "$target_rel" =~ ^[[:space:]]*# ]] && continue
    src_path="$LOCAL_DIR/$src_rel"
    if [[ ! -e "$src_path" ]]; then
      echo "PRECHECK_MISSING_SOURCE: $target_rel -> $src_path" >&2
      missing_manifest_sources=$((missing_manifest_sources + 1))
    fi
  done < "$manifest_file"
  if [[ "$missing_manifest_sources" -gt 0 ]]; then
    echo "ERROR: local manifest precheck failed with $missing_manifest_sources missing source(s)." >&2
    echo "Hint: check SYNC_LOCAL_DIR/OPENCLAW_SYNC_REMOTE_DIR overrides and current repo contents." >&2
    exit 1
  fi
else
  log "No manifest found for precheck: $manifest_file"
fi

[[ -f "$KEY_PATH" ]] || { echo "SSH key missing: $KEY_PATH" >&2; exit 1; }

AGENT_STARTED=0
KEY_ADDED=0
SSH_TARGET=""
SSH_BASE_ARGS=()

cleanup() {
  if [[ -n "$SSH_TARGET" && ${#SSH_BASE_ARGS[@]} -gt 0 ]]; then
    ssh "${SSH_BASE_ARGS[@]}" -O exit "$SSH_TARGET" >/dev/null 2>&1 || true
  fi
  if [[ "$KEY_ADDED" -eq 1 ]]; then
    ssh-add -d "$KEY_PATH" >/dev/null 2>&1 || true
  fi
  if [[ "$AGENT_STARTED" -eq 1 && -n "${SSH_AGENT_PID:-}" ]]; then
    eval "$(ssh-agent -k)" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ "$NO_AGENT" -eq 0 ]]; then
  if [[ -z "${SSH_AUTH_SOCK:-}" ]] || ! ssh-add -l >/dev/null 2>&1; then
    eval "$(ssh-agent -s)" >/dev/null
    AGENT_STARTED=1
    log "Started temporary ssh-agent"
  fi

  # Add key only if not already loaded.
  if ! ssh-add -l 2>/dev/null | grep -Fq "$(basename "$KEY_PATH")"; then
    ssh-add -t "$TTL" "$KEY_PATH" >/dev/null
    KEY_ADDED=1
    log "Loaded key for ${TTL}: $KEY_PATH"
  fi
fi

SSH_TARGET="${USER_NAME}@${HOST}"
CONTROL_SOCKET="${TMPDIR:-/tmp}/openclaw-sync-${USER_NAME}@${HOST}"
SSH_BASE_ARGS=( -i "$KEY_PATH" -o ControlMaster=auto -o ControlPersist=5m -o ControlPath="$CONTROL_SOCKET" )

REMOTE_HOME="$(ssh "${SSH_BASE_ARGS[@]}" "$SSH_TARGET" 'printf "%s" "$HOME"')"
if [[ "$REMOTE_DIR" == "~/"* ]]; then
  REMOTE_DIR_ABS="${REMOTE_HOME}/${REMOTE_DIR#~/}"
else
  REMOTE_DIR_ABS="$REMOTE_DIR"
fi

log "Ensuring remote directory exists: ${REMOTE_DIR_ABS}"
ssh "${SSH_BASE_ARGS[@]}" "$SSH_TARGET" "mkdir -p \"${REMOTE_DIR_ABS}\""

RSYNC_ARGS=( -avz )
[[ "$DELETE_MODE" -eq 1 ]] && RSYNC_ARGS+=( --delete )
[[ "$DRY_RUN" -eq 1 ]] && RSYNC_ARGS+=( --dry-run )

# Always exclude local VCS metadata from deployment sync.
RSYNC_EXCLUDES=( --exclude ".git/" )

log "Syncing ${LOCAL_DIR} -> ${SSH_TARGET}:${REMOTE_DIR_ABS}/"
rsync "${RSYNC_ARGS[@]}" "${RSYNC_EXCLUDES[@]}" -e "ssh -i ${KEY_PATH} -o ControlMaster=auto -o ControlPersist=5m -o ControlPath=${CONTROL_SOCKET}" \
  "$LOCAL_DIR" "${SSH_TARGET}:${REMOTE_DIR_ABS}/"

log "Sync complete"

if [[ "$NO_LINKS" -eq 0 ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "Skipping remote link deploy/verify because --dry-run is enabled"
  else
    if [[ "$RUNTIME_MODE" == "installed" ]]; then
      remote_install="$REMOTE_DIR_ABS/scripts/install-runtime.sh"
      log "Installing runtime payload on remote (installed mode)"
      ssh "${SSH_BASE_ARGS[@]}" "$SSH_TARGET" \
        "/usr/local/bin/bash \"$remote_install\" --source \"$REMOTE_DIR_ABS\" --prefix \"$INSTALL_PREFIX\""
      log "Remote install+deploy+verify complete (installed mode)"
    else
      remote_generate="$REMOTE_DIR_ABS/scripts/generate-manifest"
      remote_deploy="$REMOTE_DIR_ABS/scripts/deploy-runtime-links.sh"
      remote_verify="$REMOTE_DIR_ABS/scripts/verify-runtime-links.sh"
      log "Regenerating runtime manifest on remote"
      ssh "${SSH_BASE_ARGS[@]}" "$SSH_TARGET" "/usr/local/bin/bash \"$remote_generate\""
      log "Deploying runtime links on remote"
      ssh "${SSH_BASE_ARGS[@]}" "$SSH_TARGET" "/usr/local/bin/bash \"$remote_deploy\""
      log "Verifying runtime links on remote"
      ssh "${SSH_BASE_ARGS[@]}" "$SSH_TARGET" "/usr/local/bin/bash \"$remote_verify\""
      log "Remote deploy+verify complete (repo mode)"
    fi
  fi
fi
