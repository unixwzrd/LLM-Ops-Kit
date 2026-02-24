#!/usr/bin/env bash
set -euo pipefail

TEMPLATE_PATH="${1:-/Volumes/mps/bin/chatml-tools.jinja}"
HISTORY_DIR="${2:-/Volumes/mps/bin/.jinja-history}"
MODE="${3:-snapshot}"

if [[ ! -f "$TEMPLATE_PATH" ]]; then
  echo "Template not found: $TEMPLATE_PATH" >&2
  exit 1
fi

mkdir -p "$HISTORY_DIR"

stamp="$(date +%Y%m%d-%H%M%S)"
base="$(basename "$TEMPLATE_PATH")"
latest="$HISTORY_DIR/${base}.latest"
new_file="$HISTORY_DIR/${base}.${stamp}.jinja"

case "$MODE" in
  snapshot)
    cp "$TEMPLATE_PATH" "$new_file"
    ln -sfn "$new_file" "$latest"
    echo "Saved: $new_file"
    ;;
  list)
    ls -1t "$HISTORY_DIR" | sed -n '1,50p'
    ;;
  diff-last)
    last_two=( $(ls -1t "$HISTORY_DIR"/${base}.*.jinja 2>/dev/null | head -n 2) )
    if [[ ${#last_two[@]} -lt 2 ]]; then
      echo "Need at least 2 snapshots in $HISTORY_DIR" >&2
      exit 1
    fi
    diff -u "${last_two[1]}" "${last_two[0]}" || true
    ;;
  *)
    echo "Usage: $0 [template_path] [history_dir] [snapshot|list|diff-last]" >&2
    exit 1
    ;;
esac
