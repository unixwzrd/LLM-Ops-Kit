#!/usr/bin/env bash
set -euo pipefail

MODE="symlink"
if [[ "${1:-}" == "--sync" ]]; then
  MODE="sync"
fi

BIN_DIR="${BIN_DIR:-$HOME/bin}"
REPO_DIR="${REPO_DIR:-$HOME/projects/agent-work}"
mkdir -p "$BIN_DIR"

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

link_one "$BIN_DIR/gateway" "$REPO_DIR/scripts/gateway"
link_one "$BIN_DIR/proxy" "$REPO_DIR/scripts/proxy"
link_one "$BIN_DIR/openclaw-stack" "$REPO_DIR/scripts/openclaw-stack"
link_one "$BIN_DIR/openclaw-report" "$REPO_DIR/scripts/openclaw-report.sh"
link_one "$BIN_DIR/sync-agent-work" "$REPO_DIR/scripts/sync-agent-work.sh"
link_one "$BIN_DIR/openai-proxy-tap" "$REPO_DIR/bin/openai-proxy-tap"
link_one "$BIN_DIR/Qwen3" "$REPO_DIR/scripts/Qwen3"
link_one "$BIN_DIR/BGEen" "$REPO_DIR/scripts/BGEen"
link_one "$BIN_DIR/node-hygiene" "$REPO_DIR/bin/node-hygiene.sh"

# Remove deprecated names in BIN_DIR only.
for old in \
  "$BIN_DIR/openclaw-start.sh" "$BIN_DIR/sync-agent-work.sh" "$BIN_DIR/node-hygiene.sh" \
  "$BIN_DIR/openclaw-report.sh" "$BIN_DIR/openclaw-stack.sh" \
  "$BIN_DIR/StartQwen3" "$BIN_DIR/StartBGEen" "$BIN_DIR/StopQwen3" "$BIN_DIR/StopBGEen" \
  "$BIN_DIR/run-openclaw-server.sh" "$BIN_DIR/run-openclaw-embedding.sh"; do
  [ -L "$old" ] && rm -f "$old"
done
