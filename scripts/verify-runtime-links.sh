#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="${BIN_DIR:-$HOME/bin}"
REPO_DIR="${REPO_DIR:-$HOME/projects/agent-work}"

fail=0

check_one() {
  local target="$1"
  local expected="$2"

  if [[ ! -e "$target" ]]; then
    echo "MISSING: $target -> $expected"
    fail=1
    return
  fi
  if [[ ! -L "$target" ]]; then
    echo "DRIFT (not symlink): $target"
    fail=1
    return
  fi
  local actual
  actual="$(readlink "$target")"
  if [[ "$actual" != "$expected" ]]; then
    echo "DRIFT (wrong target): $target -> $actual (expected $expected)"
    fail=1
  else
    echo "OK: $target -> $actual"
  fi
}

check_one "$BIN_DIR/gateway" "$REPO_DIR/scripts/gateway"
check_one "$BIN_DIR/proxy" "$REPO_DIR/scripts/proxy"
check_one "$BIN_DIR/openclaw-stack" "$REPO_DIR/scripts/openclaw-stack"
check_one "$BIN_DIR/openclaw-report" "$REPO_DIR/scripts/openclaw-report.sh"
check_one "$BIN_DIR/sync-agent-work" "$REPO_DIR/scripts/sync-agent-work.sh"
check_one "$BIN_DIR/openai-proxy-tap" "$REPO_DIR/bin/openai-proxy-tap"
check_one "$BIN_DIR/Qwen3" "$REPO_DIR/scripts/Qwen3"
check_one "$BIN_DIR/BGEen" "$REPO_DIR/scripts/BGEen"
check_one "$BIN_DIR/node-hygiene" "$REPO_DIR/bin/node-hygiene.sh"

for old in \
  "$BIN_DIR/openclaw-start.sh" "$BIN_DIR/sync-agent-work.sh" "$BIN_DIR/node-hygiene.sh" \
  "$BIN_DIR/openclaw-report.sh" "$BIN_DIR/openclaw-stack.sh" \
  "$BIN_DIR/StartQwen3" "$BIN_DIR/StartBGEen" "$BIN_DIR/StopQwen3" "$BIN_DIR/StopBGEen" \
  "$BIN_DIR/run-openclaw-server.sh" "$BIN_DIR/run-openclaw-embedding.sh"; do
  if [[ -e "$old" ]]; then
    echo "DEPRECATED_PRESENT: $old"
    fail=1
  fi
done

exit "$fail"
