#!/usr/bin/env bash
set -euo pipefail

MODE="symlink"
if [[ "${1:-}" == "--sync" ]]; then
  MODE="sync"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_FILE="${MANIFEST_FILE:-$SCRIPT_DIR/runtime-links.manifest}"

BIN_DIR="${BIN_DIR:-$HOME/bin}"
REPO_DIR="${REPO_DIR:-$HOME/projects/agent-work}"
mkdir -p "$BIN_DIR"

if [[ ! -f "$MANIFEST_FILE" ]]; then
  echo "Manifest not found: $MANIFEST_FILE" >&2
  exit 2
fi

link_one() {
  local target="$1"
  local src="$2"
  if [[ "$MODE" == "symlink" ]]; then
    ln -sfn "$src" "$target"
    echo "LINKED: $target -> $src"
  else
    cp "$src" "$target"
    chmod +x "$target"
    echo "SYNCED: $target <= $src"
  fi
}

while IFS='|' read -r target_rel src_rel; do
  [[ -z "${target_rel:-}" ]] && continue
  [[ "$target_rel" =~ ^[[:space:]]*# ]] && continue

  target="$BIN_DIR/$target_rel"
  src="$REPO_DIR/$src_rel"
  if [[ ! -e "$src" ]]; then
    echo "SKIP_MISSING_SOURCE: $target -> $src" >&2
    continue
  fi
  link_one "$target" "$src"
done < "$MANIFEST_FILE"

# Remove deprecated names in BIN_DIR only.
for old in \
  "$BIN_DIR/openclaw-start.sh" "$BIN_DIR/sync-agent-work.sh" "$BIN_DIR/node-hygiene.sh" \
  "$BIN_DIR/openclaw-report.sh" "$BIN_DIR/openclaw-stack.sh" \
  "$BIN_DIR/StartQwen3" "$BIN_DIR/StartBGEen" "$BIN_DIR/StopQwen3" "$BIN_DIR/StopBGEen" \
  "$BIN_DIR/run-openclaw-server.sh" "$BIN_DIR/run-openclaw-embedding.sh"; do
  [ -L "$old" ] && rm -f "$old"
done
