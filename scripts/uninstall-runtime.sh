#!/usr/bin/env bash
set -euo pipefail

INSTALL_BASE="${LLMOPS_INSTALL_BASE:-$HOME/.local/llm-ops}"
PUBLIC_BIN_DIR="${LLMOPS_PUBLIC_BIN_DIR:-$HOME/.local/bin}"
CONFIG_HOME="${LLMOPS_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/llm-ops}"
DATA_HOME="${LLMOPS_DATA_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/llm-ops}"
STATE_HOME="${LLMOPS_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/llm-ops}"
CACHE_HOME="${LLMOPS_CACHE_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/llm-ops}"
PURGE=0

usage() {
  cat <<'USAGE'
Usage: uninstall-runtime.sh [options]

Options:
  --prefix <path>          Install root
  --public-bin-dir <path>  Public command directory
  --config-home <path>     Canonical configuration root
  --data-home <path>       Data root
  --state-home <path>      State root
  --cache-home <path>      Cache root
  --purge                  Also remove configuration, data, state, and cache
  -h, --help               Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) INSTALL_BASE="$2"; shift 2 ;;
    --public-bin-dir) PUBLIC_BIN_DIR="$2"; shift 2 ;;
    --config-home) CONFIG_HOME="$2"; shift 2 ;;
    --data-home) DATA_HOME="$2"; shift 2 ;;
    --state-home) STATE_HOME="$2"; shift 2 ;;
    --cache-home) CACHE_HOME="$2"; shift 2 ;;
    --purge) PURGE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "uninstall-runtime.sh: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

remove_managed_link() {
  local path="$1" target=""
  [[ -L "$path" ]] || return 0
  target="$(readlink "$path")"
  case "$target" in
    "$INSTALL_BASE"/*) rm -f "$path" ;;
  esac
}

remove_managed_link "$PUBLIC_BIN_DIR/llmops"
if [[ -d "$INSTALL_BASE/bin" ]]; then
  for path in "$INSTALL_BASE/bin"/*; do
    [[ -e "$path" || -L "$path" ]] || continue
    remove_managed_link "$path"
  done
fi
rm -rf "$INSTALL_BASE"
rm -f "$STATE_HOME/install.json"

if [[ "$PURGE" -eq 1 ]]; then
  rm -rf "$CONFIG_HOME" "$DATA_HOME" "$STATE_HOME" "$CACHE_HOME"
fi

echo "UNINSTALLED: $INSTALL_BASE"
if [[ "$PURGE" -eq 1 ]]; then echo "PURGED: configuration data state cache"; fi
