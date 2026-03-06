#!/usr/bin/env bash
set -euo pipefail

MODE="symlink"
if [[ "${1:-}" == "--sync" ]]; then
  MODE="sync"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_FILE="${MANIFEST_FILE:-$SCRIPT_DIR/runtime-links.manifest}"

BIN_DIR="${BIN_DIR:-$HOME/bin}"
REPO_DIR="${REPO_DIR:-$HOME/projects/LLM-Ops-Kit}"
mkdir -p "$BIN_DIR"

if [[ ! -f "$MANIFEST_FILE" ]]; then
  echo "Manifest not found: $MANIFEST_FILE" >&2
  exit 2
fi

conflicts=0

link_one() {
  local target="$1"
  local src="$2"
  local actual=""
  local healed=""
  if [[ "$MODE" == "symlink" ]]; then
    if [[ -e "$target" || -L "$target" ]]; then
      if [[ -L "$target" ]]; then
        actual="$(readlink "$target" 2>/dev/null || true)"
        if [[ "$actual" == "$src" ]]; then
          echo "OK_ALREADY: $target -> $src"
          return 0
        fi
        # Auto-heal symlinks left behind by repo rename:
        # ~/projects/OpenClaw-Ops-Toolkit -> ~/projects/LLM-Ops-Kit
        healed="${actual/\/projects\/OpenClaw-Ops-Toolkit\//\/projects\/LLM-Ops-Kit\/}"
        if [[ "$healed" == "$src" ]]; then
          ln -sfn "$src" "$target"
          echo "HEALED_RENAME_LINK: $target -> $src"
          return 0
        fi
        echo "CONFLICT: $target -> $actual (expected $src); skipped." >&2
        conflicts=$((conflicts + 1))
        return 1
      fi
      echo "CONFLICT: $target exists and is not a symlink; skipped." >&2
      conflicts=$((conflicts + 1))
      return 1
    fi
    ln -s "$src" "$target"
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
  link_one "$target" "$src" || true
done < "$MANIFEST_FILE"

# Remove deprecated names in BIN_DIR only.
for old in \
  "$BIN_DIR/openclaw-start.sh" "$BIN_DIR/sync-agent-work" "$BIN_DIR/sync-agent-work.sh" "$BIN_DIR/sync-OpenClaw-Ops-Toolkit" "$BIN_DIR/sync-OpenClaw-Ops-Toolkit.sh" "$BIN_DIR/sync-LLM-Ops-Kit" "$BIN_DIR/sync-LLM-Ops-Kit.sh" "$BIN_DIR/sync-ops-scripts.sh" "$BIN_DIR/node-hygiene.sh" \
  "$BIN_DIR/openclaw-report.sh" "$BIN_DIR/openclaw-stack.sh" \
  "$BIN_DIR/StartQwen3" "$BIN_DIR/StartBGEen" "$BIN_DIR/StopQwen3" "$BIN_DIR/StopBGEen" \
  "$BIN_DIR/run-openclaw-server.sh" "$BIN_DIR/run-openclaw-embedding.sh"; do
  [ -L "$old" ] && rm -f "$old"
done

# Remove dead symlinks in BIN_DIR to keep runtime command surface clean.
while IFS= read -r dead; do
  [[ -n "$dead" ]] || continue
  rm -f "$dead"
  echo "REMOVED_DEADLINK: $dead"
done < <(find "$BIN_DIR" -maxdepth 1 -type l ! -exec test -e {} \; -print)

if [[ "$conflicts" -gt 0 ]]; then
  echo "ERROR: link conflicts detected: $conflicts" >&2
  exit 1
fi
