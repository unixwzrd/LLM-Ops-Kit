#!/usr/bin/env bash
set -euo pipefail

MODE="dry-run"
ARCHIVE_HOME_PROJECT=0
CLEAN_NODE_GYP=0

for arg in "$@"; do
  case "$arg" in
    --apply) MODE="apply" ;;
    --archive-home-project) ARCHIVE_HOME_PROJECT=1 ;;
    --clean-node-gyp-cache) CLEAN_NODE_GYP=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: node-hygiene.sh [--apply] [--archive-home-project] [--clean-node-gyp-cache]

Default mode is dry-run (prints what would change).

Options:
  --apply                  Make changes.
  --archive-home-project   Move ~/package.json and ~/package-lock.json to a timestamped backup folder.
  --clean-node-gyp-cache   Also remove ~/Library/Caches/node-gyp.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

HOME_DIR="${HOME}"
BACKUP_ROOT="${HOME_DIR}/.openclaw/backups"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/node-home-project-${TS}"
NPM_GLOBAL_PREFIX="${HOME_DIR}/.npm-global"

say() {
  printf '%s\n' "$*"
}

run_cmd() {
  if [[ "${MODE}" == "apply" ]]; then
    "$@"
  else
    say "DRY-RUN: $*"
  fi
}

path_size() {
  local path="$1"
  if [[ -e "$path" ]]; then
    du -sh "$path" 2>/dev/null | awk '{print $1}'
  else
    echo "0B"
  fi
}

remove_path() {
  local path="$1"
  if [[ -e "$path" ]]; then
    run_cmd rm -rf "$path"
  else
    say "SKIP (missing): $path"
  fi
}

ensure_line() {
  local file="$1"
  local line="$2"
  if [[ -f "$file" ]] && grep -Fqx "$line" "$file"; then
    say "OK: line already present in $file"
    return 0
  fi
  if [[ "${MODE}" == "apply" ]]; then
    touch "$file"
    printf '%s\n' "$line" >> "$file"
    say "UPDATED: $file"
  else
    say "DRY-RUN: append line to $file: $line"
  fi
}

say "== Node Hygiene (${MODE}) =="
say ""
say "Current global npm prefix: $(npm config get prefix 2>/dev/null || echo unknown)"
say "Current global npm root:   $(npm root -g 2>/dev/null || echo unknown)"
say ""
say "Current sizes:"
for p in \
  "${HOME_DIR}/node_modules" \
  "${HOME_DIR}/.npm" \
  "${HOME_DIR}/Library/pnpm" \
  "${HOME_DIR}/Library/Caches/pnpm" \
  "${HOME_DIR}/Library/Caches/node-gyp" \
  "/usr/local/lib/node_modules"; do
  say "  $(printf '%-45s' "$p") $(path_size "$p")"
done
say ""

if [[ "$ARCHIVE_HOME_PROJECT" -eq 1 ]]; then
  if [[ -f "${HOME_DIR}/package.json" || -f "${HOME_DIR}/package-lock.json" ]]; then
    run_cmd mkdir -p "$BACKUP_DIR"
    [[ -f "${HOME_DIR}/package.json" ]] && run_cmd mv "${HOME_DIR}/package.json" "$BACKUP_DIR/"
    [[ -f "${HOME_DIR}/package-lock.json" ]] && run_cmd mv "${HOME_DIR}/package-lock.json" "$BACKUP_DIR/"
    say "Archived home-level project files to: $BACKUP_DIR"
  else
    say "No home-level package files found to archive."
  fi
else
  say "Home-level package files left untouched (use --archive-home-project to move them)."
fi
say ""

say "Cleaning high-churn cache/deps paths..."
remove_path "${HOME_DIR}/node_modules"
remove_path "${HOME_DIR}/.npm/_npx"
remove_path "${HOME_DIR}/Library/Caches/pnpm"
if [[ "$CLEAN_NODE_GYP" -eq 1 ]]; then
  remove_path "${HOME_DIR}/Library/Caches/node-gyp"
else
  say "Skipped node-gyp cache (add --clean-node-gyp-cache to include)."
fi
say ""

say "Pruning package-manager caches..."
if command -v npm >/dev/null 2>&1; then
  if [[ "${MODE}" == "apply" ]]; then
    npm cache clean --force || true
  else
    say "DRY-RUN: npm cache clean --force"
  fi
fi
if command -v pnpm >/dev/null 2>&1; then
  if [[ "${MODE}" == "apply" ]]; then
    pnpm store prune || true
  else
    say "DRY-RUN: pnpm store prune"
  fi
fi
say ""

say "Configuring user-local global npm prefix (${NPM_GLOBAL_PREFIX})..."
run_cmd mkdir -p "${NPM_GLOBAL_PREFIX}/bin"
if [[ "${MODE}" == "apply" ]]; then
  npm config set prefix "${NPM_GLOBAL_PREFIX}"
else
  say "DRY-RUN: npm config set prefix ${NPM_GLOBAL_PREFIX}"
fi
ensure_line "${HOME_DIR}/.zprofile" 'export PATH="$HOME/.npm-global/bin:$PATH"'
ensure_line "${HOME_DIR}/.bashrc" 'export PATH="$HOME/.npm-global/bin:$PATH"'
say ""

say "Post-clean checks:"
say "  npm prefix -g  => $(npm prefix -g 2>/dev/null || echo unknown)"
say "  npm root -g    => $(npm root -g 2>/dev/null || echo unknown)"
say ""
say "Next steps for pnpm projects:"
say "  cd <project> && pnpm install"
say ""
say "Done."
