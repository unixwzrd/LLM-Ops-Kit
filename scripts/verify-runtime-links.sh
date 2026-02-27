#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_FILE="${MANIFEST_FILE:-$SCRIPT_DIR/runtime-links.manifest}"

BIN_DIR="${BIN_DIR:-$HOME/bin}"
REPO_DIR="${REPO_DIR:-$HOME/projects/agent-work}"

if [[ ! -f "$MANIFEST_FILE" ]]; then
  echo "Manifest not found: $MANIFEST_FILE" >&2
  exit 2
fi

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

while IFS='|' read -r target_rel src_rel; do
  [[ -z "${target_rel:-}" ]] && continue
  [[ "$target_rel" =~ ^[[:space:]]*# ]] && continue
  check_one "$BIN_DIR/$target_rel" "$REPO_DIR/$src_rel"
done < "$MANIFEST_FILE"

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
