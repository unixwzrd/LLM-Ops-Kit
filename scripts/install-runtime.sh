#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -h "$SOURCE" ]]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
SOURCE_DIR_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_DIR="${LLMOPS_SOURCE_DIR:-$SOURCE_DIR_DEFAULT}"
INSTALL_BASE="${LLMOPS_INSTALL_BASE:-$HOME/.llm-ops}"
INSTALL_DIR="$INSTALL_BASE/current"
BIN_DIR="${BIN_DIR:-$HOME/bin}"
STATE_FILE="${LLMOPS_STATE_FILE:-$HOME/.llm-ops/runtime-state.env}"
NO_LINKS=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --source <path>      Source repo directory (default: $SOURCE_DIR_DEFAULT)
  --prefix <path>      Install base dir (default: ~/.llm-ops)
  --bin-dir <path>     Runtime bin dir (default: ~/bin)
  --state-file <path>  Runtime state file (default: ~/.llm-ops/runtime-state.env)
  --no-links           Install files only; skip link deploy/verify
  -h, --help           Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE_DIR="$2"; shift 2 ;;
    --prefix) INSTALL_BASE="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --state-file) STATE_FILE="$2"; shift 2 ;;
    --no-links) NO_LINKS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

INSTALL_DIR="$INSTALL_BASE/current"
STAGING_DIR="$INSTALL_BASE/.staging.$$"
BACKUP_DIR="$INSTALL_BASE/backups/$(date +%Y%m%d-%H%M%S)"

[[ -d "$SOURCE_DIR/scripts" ]] || { echo "Missing source scripts dir: $SOURCE_DIR/scripts" >&2; exit 1; }
[[ -d "$SOURCE_DIR/bin" ]] || { echo "Missing source bin dir: $SOURCE_DIR/bin" >&2; exit 1; }
[[ -x "$SOURCE_DIR/scripts/deploy-runtime-links.sh" ]] || {
  echo "Missing deploy script in source: $SOURCE_DIR/scripts/deploy-runtime-links.sh" >&2
  exit 1
}

mkdir -p "$INSTALL_BASE" "$BIN_DIR"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

echo "Installing runtime payload from: $SOURCE_DIR"
rsync -a --delete "$SOURCE_DIR/scripts/" "$STAGING_DIR/scripts/"
rsync -a --delete "$SOURCE_DIR/bin/" "$STAGING_DIR/bin/"

if [[ -d "$INSTALL_DIR" ]]; then
  mkdir -p "$(dirname "$BACKUP_DIR")"
  mv "$INSTALL_DIR" "$BACKUP_DIR"
  echo "Backed up previous runtime to: $BACKUP_DIR"
fi

mv "$STAGING_DIR" "$INSTALL_DIR"
echo "Installed runtime to: $INSTALL_DIR"

if [[ "$NO_LINKS" -eq 0 ]]; then
  pushd "$INSTALL_DIR/scripts" >/dev/null
  ./generate-manifest
  BIN_DIR="$BIN_DIR" RUNTIME_DIR="$INSTALL_DIR" ./deploy-runtime-links.sh --replace-managed-links
  BIN_DIR="$BIN_DIR" RUNTIME_DIR="$INSTALL_DIR" ./verify-runtime-links.sh
  popd >/dev/null
fi

if [[ -f "$INSTALL_DIR/scripts/lib/common.sh" ]]; then
  # shellcheck disable=SC1090
  . "$INSTALL_DIR/scripts/lib/common.sh"
  load_shell_env
  prune_runtime_backups
fi

mkdir -p "$(dirname "$STATE_FILE")"
cat > "$STATE_FILE" <<EOF
LLMOPS_INSTALL_MODE=installed
LLMOPS_INSTALL_BASE=$INSTALL_BASE
LLMOPS_INSTALL_DIR=$INSTALL_DIR
LLMOPS_BIN_DIR=$BIN_DIR
LLMOPS_SOURCE_DIR=$SOURCE_DIR
LLMOPS_UPDATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
echo "WROTE_STATE: $STATE_FILE"

echo "Install complete."
