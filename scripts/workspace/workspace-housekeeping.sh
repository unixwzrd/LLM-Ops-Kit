#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEM_DIR="$ROOT/memory"
TODAY="$(date +%Y%m%d-%H%M%S)"

usage() {
  cat <<USAGE
Usage: workspace-housekeeping.sh <command> [options]

Commands:
  report-stale [--days N]
  report-unreferenced
  archive-stale [--days N]
  snapshot-commit [--message MSG]

Defaults:
  --days 30
USAGE
}

days_arg() {
  local days=30
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --days) days="$2"; shift 2 ;;
      *) shift ;;
    esac
  done
  echo "$days"
}

report_stale() {
  local days
  days="$(days_arg "$@")"
  find "$MEM_DIR" -type f -name '*.md' -mtime "+$days" | sort
}

report_unreferenced() {
  local all refs
  all="$(mktemp)"
  refs="$(mktemp)"

  find "$MEM_DIR" -type f -name '*.md' | sed "s#^$ROOT/##" | sort > "$all"

  # Collect markdown relative links like (memory/...), (./...), (../...)
  rg -No "\((\.?\.?/)?memory/[^)]+\.md\)" "$MEM_DIR" \
    | sed -E 's/^.*\(([^)]+)\).*$/\1/' \
    | sed 's#^\./##' \
    | sed 's#^\.\./##' \
    | sort -u > "$refs" || true

  comm -23 "$all" "$refs"

  rm -f "$all" "$refs"
}

archive_stale() {
  local days
  days="$(days_arg "$@")"
  local target="$MEM_DIR/archive/$TODAY"
  mkdir -p "$target"

  while IFS= read -r file; do
    # Keep policy and index files in place.
    case "$file" in
      "$MEM_DIR/policies/"*|"$ROOT/MEMORY.md")
        continue
        ;;
    esac

    rel="${file#$MEM_DIR/}"
    mkdir -p "$target/$(dirname "$rel")"
    mv "$file" "$target/$rel"
    echo "archived: $rel"
  done < <(find "$MEM_DIR" -type f -name '*.md' -mtime "+$days")
}

snapshot_commit() {
  local msg="workspace snapshot: $TODAY"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --message) msg="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "not a git repo: $ROOT" >&2
    return 1
  fi

  if [[ -z "$(git -C "$ROOT" status --porcelain)" ]]; then
    echo "no changes"
    return 0
  fi

  git -C "$ROOT" add -A
  git -C "$ROOT" commit -m "$msg"
}

main() {
  cmd="${1:-}"
  shift || true
  case "$cmd" in
    report-stale) report_stale "$@" ;;
    report-unreferenced) report_unreferenced ;;
    archive-stale) archive_stale "$@" ;;
    snapshot-commit) snapshot_commit "$@" ;;
    ""|-h|--help|help) usage ;;
    *)
      echo "unknown command: $cmd" >&2
      usage
      exit 2
      ;;
  esac
}

main "$@"
