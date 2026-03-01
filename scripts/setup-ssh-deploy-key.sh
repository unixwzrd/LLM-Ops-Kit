#!/usr/bin/env bash
set -euo pipefail

KEY_PATH="${KEY_PATH:-$HOME/.ssh/id_ed25519_openclaw_deploy}"
KEY_COMMENT="${KEY_COMMENT:-openclaw-deploy}"
TTL="${TTL:-20m}"
REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_USER="${REMOTE_USER:-$USER}"
INSTALL_REMOTE=0

usage() {
  cat <<'USAGE'
Usage: setup-ssh-deploy-key.sh [options]

Options:
  --key <path>            Private key path (default: ~/.ssh/id_ed25519_openclaw_deploy)
  --comment <text>        Key comment (default: openclaw-deploy)
  --ttl <duration>        ssh-add lifetime (default: 20m)
  --host <host>           Remote host for optional install
  --user <user>           Remote user (default: current user)
  --install-remote        Install public key to remote authorized_keys
  -h, --help              Show help

Behavior:
  - Creates key if missing.
  - Prints public key and verification commands.
  - If --install-remote is provided with --host, installs key remotely.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key) KEY_PATH="$2"; shift 2 ;;
    --comment) KEY_COMMENT="$2"; shift 2 ;;
    --ttl) TTL="$2"; shift 2 ;;
    --host) REMOTE_HOST="$2"; shift 2 ;;
    --user) REMOTE_USER="$2"; shift 2 ;;
    --install-remote) INSTALL_REMOTE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

if [[ ! -f "$KEY_PATH" ]]; then
  ssh-keygen -t ed25519 -f "$KEY_PATH" -C "$KEY_COMMENT" -N ""
  echo "Created key: $KEY_PATH"
else
  echo "Key already exists: $KEY_PATH"
fi

chmod 600 "$KEY_PATH"
chmod 644 "$KEY_PATH.pub"

if [[ -z "${SSH_AUTH_SOCK:-}" ]]; then
  eval "$(ssh-agent -s)" >/dev/null
fi
ssh-add -t "$TTL" "$KEY_PATH" >/dev/null
echo "Loaded key into agent with TTL=$TTL"

if [[ "$INSTALL_REMOTE" -eq 1 ]]; then
  if [[ -z "$REMOTE_HOST" ]]; then
    echo "--install-remote requires --host" >&2
    exit 2
  fi
  cat "$KEY_PATH.pub" | ssh "$REMOTE_USER@$REMOTE_HOST" \
    'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
  echo "Installed public key on $REMOTE_USER@$REMOTE_HOST"
fi

echo
echo "Public key:"
cat "$KEY_PATH.pub"
echo
echo "Verify:"
if [[ -n "$REMOTE_HOST" ]]; then
  echo "  ssh $REMOTE_USER@$REMOTE_HOST 'echo SSH_OK'"
else
  echo "  ssh <user>@<host> 'echo SSH_OK'"
fi
echo
echo "Remove key from agent when done:"
echo "  ssh-add -d $KEY_PATH"

