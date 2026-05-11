#!/usr/bin/env bash
set -euo pipefail

INSTALL_BASE="${LLMOPS_INSTALL_BASE:-$HOME/.local/llm-ops}"
INSTALL_DIR="$INSTALL_BASE/current"
BIN_DIR="${BIN_DIR:-${LLMOPS_BIN_DIR:-$HOME/.local/llm-ops/bin}}"
PUBLIC_BIN_DIR="${LLMOPS_PUBLIC_BIN_DIR:-$HOME/.local/bin}"
STATE_HOME="${LLMOPS_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/llm-ops}"
STATE_FILE="${LLMOPS_STATE_FILE:-$STATE_HOME/runtime-state.env}"
KEEP_FILES=0
BIN_DIR_EXPLICIT=0
PUBLIC_BIN_DIR_EXPLICIT=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --prefix <path>    Install base dir (default: ~/.local/llm-ops)
  --bin-dir <path>   Managed runtime bin dir (default: ~/.local/llm-ops/bin)
  --public-bin-dir <path> Public launcher dir (default: ~/.local/bin)
  --state-file <path> Runtime state file (default: ~/.local/state/llm-ops/runtime-state.env)
  --keep-files       Keep installed runtime files; remove links only
  -h, --help         Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) INSTALL_BASE="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; BIN_DIR_EXPLICIT=1; shift 2 ;;
    --public-bin-dir) PUBLIC_BIN_DIR="$2"; PUBLIC_BIN_DIR_EXPLICIT=1; shift 2 ;;
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

if [[ "$BIN_DIR_EXPLICIT" -eq 0 || "$PUBLIC_BIN_DIR_EXPLICIT" -eq 1 ]]; then
  public_launcher="$PUBLIC_BIN_DIR/llmops"
  expected_public="$INSTALL_DIR/scripts/llmops"
  if [[ -L "$public_launcher" ]]; then
    actual_public="$(readlink "$public_launcher" 2>/dev/null || true)"
    if [[ "$actual_public" == "$expected_public" ]]; then
      rm -f "$public_launcher"
      echo "REMOVED_PUBLIC_LINK: $public_launcher -> $actual_public"
    fi
  fi
fi

if [[ -f "$STATE_FILE" ]]; then
  rm -f "$STATE_FILE"
  echo "REMOVED_STATE: $STATE_FILE"
fi

echo "Uninstall complete. links_removed=$removed"
