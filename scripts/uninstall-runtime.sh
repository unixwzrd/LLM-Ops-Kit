#!/usr/bin/env bash
set -euo pipefail

INSTALL_BASE="${OPENCLAW_OPS_INSTALL_BASE:-$HOME/.openclaw-ops}"
INSTALL_DIR="$INSTALL_BASE/current"
BIN_DIR="${BIN_DIR:-$HOME/bin}"
STATE_FILE="${OPENCLAW_OPS_STATE_FILE:-$HOME/.openclaw-ops/runtime-state.env}"
KEEP_FILES=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --prefix <path>    Install base dir (default: ~/.openclaw-ops)
  --bin-dir <path>   Runtime bin dir (default: ~/bin)
  --state-file <path> Runtime state file (default: ~/.openclaw-ops/runtime-state.env)
  --keep-files       Keep installed runtime files; remove links only
  -h, --help         Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) INSTALL_BASE="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --state-file) STATE_FILE="$2"; shift 2 ;;
    --keep-files) KEEP_FILES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

INSTALL_DIR="$INSTALL_BASE/current"
MANIFEST_FILE="$INSTALL_DIR/scripts/runtime-links.manifest"

if [[ ! -f "$MANIFEST_FILE" ]]; then
  echo "Manifest not found: $MANIFEST_FILE" >&2
  echo "Nothing to uninstall."
  exit 0
fi

removed=0

while IFS='|' read -r target_rel src_rel; do
  [[ -z "${target_rel:-}" ]] && continue
  [[ "$target_rel" =~ ^[[:space:]]*# ]] && continue

  target="$BIN_DIR/$target_rel"
  expected="$INSTALL_DIR/$src_rel"
  if [[ -L "$target" ]]; then
    actual="$(readlink "$target" 2>/dev/null || true)"
    if [[ "$actual" == "$expected" ]]; then
      rm -f "$target"
      echo "REMOVED_LINK: $target -> $actual"
      removed=$((removed + 1))
    fi
  fi
done < "$MANIFEST_FILE"

if [[ "$KEEP_FILES" -eq 0 ]]; then
  rm -rf "$INSTALL_DIR"
  echo "REMOVED_INSTALL_DIR: $INSTALL_DIR"
fi

if [[ -f "$STATE_FILE" ]]; then
  rm -f "$STATE_FILE"
  echo "REMOVED_STATE: $STATE_FILE"
fi

echo "Uninstall complete. links_removed=$removed"
