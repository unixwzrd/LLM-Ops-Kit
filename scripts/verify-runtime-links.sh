#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_FILE="${MANIFEST_FILE:-$SCRIPT_DIR/runtime-links.manifest}"

BIN_DIR="${BIN_DIR:-$HOME/bin}"
RUNTIME_DIR="${RUNTIME_DIR:-${REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}}"

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
  check_one "$BIN_DIR/$target_rel" "$RUNTIME_DIR/$src_rel"
done < "$MANIFEST_FILE"

# Flag stale managed links no longer represented in manifest.
manifest_targets_file="$(mktemp)"
while IFS='|' read -r target_rel src_rel; do
  [[ -z "${target_rel:-}" ]] && continue
  [[ "$target_rel" =~ ^[[:space:]]*# ]] && continue
  printf '%s\n' "$target_rel" >> "$manifest_targets_file"
done < "$MANIFEST_FILE"

while IFS= read -r link_path; do
  [[ -n "$link_path" ]] || continue
  target="$(readlink "$link_path" 2>/dev/null || true)"
  case "$target" in
    "$RUNTIME_DIR"/scripts/*|"$RUNTIME_DIR"/bin/*)
      name="$(basename "$link_path")"
      if ! grep -qxF "$name" "$manifest_targets_file"; then
        echo "STALE_MANAGED_LINK: $link_path -> $target"
        fail=1
      fi
      ;;
  esac
done < <(find "$BIN_DIR" -maxdepth 1 -type l -print)

rm -f "$manifest_targets_file"

for old in \
  "$BIN_DIR/proxy" "$BIN_DIR/openai-proxy-tap" "$BIN_DIR/openclaw-start.sh" "$BIN_DIR/sync-agent-work" "$BIN_DIR/sync-agent-work.sh" "$BIN_DIR/sync-OpenClaw-Ops-Toolkit" "$BIN_DIR/sync-OpenClaw-Ops-Toolkit.sh" "$BIN_DIR/sync-LLM-Ops-Kit" "$BIN_DIR/sync-LLM-Ops-Kit.sh" "$BIN_DIR/sync-ops-scripts.sh" "$BIN_DIR/node-hygiene.sh" \
  "$BIN_DIR/openclaw-report.sh" "$BIN_DIR/openclaw-stack.sh" \
  "$BIN_DIR/StartQwen3" "$BIN_DIR/StartBGEen" "$BIN_DIR/StartBGEm3" "$BIN_DIR/StopQwen3" "$BIN_DIR/StopBGEen" "$BIN_DIR/StopBGEm3" \
  "$BIN_DIR/run-openclaw-server.sh" "$BIN_DIR/run-openclaw-embedding.sh"; do
  if [[ -e "$old" ]]; then
    echo "DEPRECATED_PRESENT: $old"
    fail=1
  fi
done

# Fail on any dead symlink in BIN_DIR, even if not part of manifest.
while IFS= read -r dead; do
  [[ -n "$dead" ]] || continue
  echo "DEADLINK: $dead -> $(readlink "$dead" 2>/dev/null || true)"
  fail=1
done < <(find "$BIN_DIR" -maxdepth 1 -type l ! -exec test -e {} \; -print)

exit "$fail"
