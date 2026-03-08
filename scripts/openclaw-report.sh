#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -h "$SOURCE" ]]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/lib/common.sh"

ensure_runtime_dirs

echo "OpenClaw Runtime Report"
echo "timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "run_dir: $OPENCLAW_RUN_DIR"
echo "log_dir: $OPENCLAW_LOG_DIR"
echo

"$SCRIPT_DIR/openclaw-stack" status
echo

echo "Recent logs:"
for log in \
  "$OPENCLAW_LOG_DIR/gateway.log" \
  "$OPENCLAW_LOG_DIR/llama-server-Qwen3VL.log" \
  "$OPENCLAW_LOG_DIR/llama-server-bge-small-en.log" \
  "$OPENCLAW_LOG_DIR/model-proxy-tap.log"; do
  if [[ -f "$log" ]]; then
    echo "--- $log"
    tail -n 5 "$log" || true
  else
    echo "--- $log (missing)"
  fi
done
