#!/usr/bin/env bash
set -euo pipefail

# Sync local agent-work repo to a remote host with short-lived key loading.
# Default: interactive + safe (no --delete unless requested).

HOST="${SYNC_HOST:-10.0.0.67}"
USER_NAME="${SYNC_USER:-miafour}"
REMOTE_DIR="${SYNC_REMOTE_DIR:-~/projects/agent-work}"
KEY_PATH="${SYNC_KEY_PATH:-$HOME/.ssh/id_ed25519_misfour_deploy}"
TTL="${SYNC_KEY_TTL:-20m}"
LOCAL_DIR="${SYNC_LOCAL_DIR:-$HOME/projects/agent-work/}"
DELETE_MODE=0
DRY_RUN=0
NO_AGENT=0
QUIET=0

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
  --quiet                  Less output
  -h, --help               Show this help

Env overrides:
  SYNC_HOST, SYNC_USER, SYNC_REMOTE_DIR, SYNC_LOCAL_DIR, SYNC_KEY_PATH, SYNC_KEY_TTL
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
    --quiet) QUIET=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

[[ -d "$LOCAL_DIR" ]] || { echo "Local dir missing: $LOCAL_DIR" >&2; exit 1; }
[[ -f "$KEY_PATH" ]] || { echo "SSH key missing: $KEY_PATH" >&2; exit 1; }

AGENT_STARTED=0
KEY_ADDED=0

cleanup() {
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

log "Ensuring remote directory exists: ${REMOTE_DIR}"
ssh -i "$KEY_PATH" "$SSH_TARGET" "mkdir -p \"${REMOTE_DIR}\""

RSYNC_ARGS=( -avz )
[[ "$DELETE_MODE" -eq 1 ]] && RSYNC_ARGS+=( --delete )
[[ "$DRY_RUN" -eq 1 ]] && RSYNC_ARGS+=( --dry-run )

log "Syncing ${LOCAL_DIR} -> ${SSH_TARGET}:${REMOTE_DIR}/"
rsync "${RSYNC_ARGS[@]}" -e "ssh -i ${KEY_PATH}" \
  "$LOCAL_DIR" "${SSH_TARGET}:${REMOTE_DIR}/"

log "Sync complete"
