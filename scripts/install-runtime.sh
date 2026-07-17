#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${LLMOPS_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTALL_BASE="${LLMOPS_INSTALL_BASE:-$HOME/.local/llm-ops}"
PUBLIC_BIN_DIR="${LLMOPS_PUBLIC_BIN_DIR:-$HOME/.local/bin}"
STATE_HOME="${LLMOPS_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/llm-ops}"
RELEASE_ID=""
REPAIR=0

INTERNAL_COMMANDS=(llmops llmops-control modelctl model-proxy tts-bridge tts runtime-maintenance)

usage() {
  cat <<'USAGE'
Usage: install-runtime.sh [options]

Options:
  --source <path>          Source checkout
  --prefix <path>          Install root (default: ~/.local/llm-ops)
  --public-bin-dir <path>  Public command directory (default: ~/.local/bin)
  --state-home <path>      State root (default: ~/.local/state/llm-ops)
  --release-id <id>        Explicit immutable release ID
  --repair                 Rebuild links for the active release only
  -h, --help               Show this help
USAGE
}

expand_path() {
  case "$1" in
    "~") printf '%s\n' "$HOME" ;;
    \~/*) printf '%s/%s\n' "$HOME" "${1#\~/}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE_DIR="$2"; shift 2 ;;
    --prefix) INSTALL_BASE="$2"; shift 2 ;;
    --public-bin-dir) PUBLIC_BIN_DIR="$2"; shift 2 ;;
    --state-home) STATE_HOME="$2"; shift 2 ;;
    --release-id) RELEASE_ID="$2"; shift 2 ;;
    --repair) REPAIR=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install-runtime.sh: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

SOURCE_DIR="$(expand_path "$SOURCE_DIR")"
INSTALL_BASE="$(expand_path "$INSTALL_BASE")"
PUBLIC_BIN_DIR="$(expand_path "$PUBLIC_BIN_DIR")"
STATE_HOME="$(expand_path "$STATE_HOME")"
CURRENT="$INSTALL_BASE/current"
PREVIOUS="$INSTALL_BASE/previous"

replace_link() {
  local source="$1" destination="$2" temporary="${2}.new.$$"
  ln -s "$source" "$temporary"
  if ! mv -fh "$temporary" "$destination" 2>/dev/null; then
    rm -f "$destination"
    mv -f "$temporary" "$destination"
  fi
}

link_runtime() {
  local root="$1" name source
  mkdir -p "$INSTALL_BASE/bin" "$PUBLIC_BIN_DIR"
  for name in "${INTERNAL_COMMANDS[@]}"; do
    source="$root/scripts/$name"
    [[ -x "$source" ]] || continue
    ln -sfn "$source" "$INSTALL_BASE/bin/$name"
  done
  ln -sfn "$root/scripts/llmops" "$PUBLIC_BIN_DIR/llmops"
}

write_state() {
  local release="$1"
  local state_file="$STATE_HOME/install.json"
  "${LLMOPS_PYTHON_BIN:-python3}" "$SOURCE_DIR/scripts/lib/llmops_install_state.py" \
    "$state_file" "$INSTALL_BASE" "$PUBLIC_BIN_DIR" "$release"
}

if [[ "$REPAIR" -eq 1 ]]; then
  [[ -L "$CURRENT" ]] || { echo "install-runtime.sh: no active installation to repair" >&2; exit 2; }
  active="$(readlink "$CURRENT")"
  [[ -d "$active" ]] || { echo "install-runtime.sh: active release is missing: $active" >&2; exit 2; }
  link_runtime "$CURRENT"
  write_state "$active"
  echo "REPAIRED: $active"
  exit 0
fi

[[ -d "$SOURCE_DIR/scripts" ]] || {
  echo "install-runtime.sh: invalid source checkout: $SOURCE_DIR" >&2
  exit 2
}

if [[ -z "$RELEASE_ID" ]]; then
  revision="$(git -C "$SOURCE_DIR" rev-parse --short HEAD 2>/dev/null || printf source)"
  RELEASE_ID="local-$(date -u +%Y%m%dT%H%M%SZ)-$revision"
fi
[[ "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "install-runtime.sh: invalid release ID" >&2; exit 2; }

release="$INSTALL_BASE/releases/$RELEASE_ID"
staging="$INSTALL_BASE/.staging-$RELEASE_ID-$$"
old=""
previous_old=""
previous_existed=0
release_created=0
switched=0

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  rm -rf "$staging"
  if [[ "$status" -ne 0 ]]; then
    if [[ "$switched" -eq 1 ]]; then
      if [[ -n "$old" ]]; then
        replace_link "$old" "$CURRENT"
      else
        rm -f "$CURRENT"
      fi
      if [[ "$previous_existed" -eq 1 ]]; then
        replace_link "$previous_old" "$PREVIOUS"
      else
        rm -f "$PREVIOUS"
      fi
    fi
    if [[ "$release_created" -eq 1 ]]; then
      rm -rf "$release"
    fi
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

[[ ! -e "$release" ]] || { echo "install-runtime.sh: release already exists: $release" >&2; exit 2; }
mkdir -p "$staging" "$INSTALL_BASE/releases"
rsync -a --delete \
  --exclude tests \
  --exclude __pycache__ \
  --exclude '*.pyc' \
  --exclude bootstrap-install.sh \
  --exclude build-release.py \
  --exclude precheck \
  "$SOURCE_DIR/scripts/" "$staging/scripts/"
for metadata in RELEASE.json release-manifest.json; do
  if [[ -f "$SOURCE_DIR/$metadata" ]]; then cp "$SOURCE_DIR/$metadata" "$staging/$metadata"; fi
done
[[ -x "$staging/scripts/llmops" && -x "$staging/scripts/llmops-control" ]] || {
  echo "install-runtime.sh: staged payload is incomplete" >&2
  exit 2
}
mv "$staging" "$release"
release_created=1
if [[ -L "$CURRENT" ]]; then
  old="$(readlink "$CURRENT")"
fi
if [[ -L "$PREVIOUS" ]]; then
  previous_old="$(readlink "$PREVIOUS")"
  previous_existed=1
fi
if [[ -n "$old" ]]; then
  replace_link "$old" "$PREVIOUS"
fi
switched=1
replace_link "$release" "$CURRENT"
link_runtime "$CURRENT"
write_state "$release"
trap - EXIT INT TERM
echo "INSTALLED: $release"
echo "CURRENT: $(readlink "$CURRENT")"
if [[ -L "$PREVIOUS" ]]; then echo "PREVIOUS: $(readlink "$PREVIOUS")"; fi
case ":$PATH:" in
  *":$PUBLIC_BIN_DIR:"*) ;;
  *) echo "PATH NOTICE: add $PUBLIC_BIN_DIR to PATH or invoke $PUBLIC_BIN_DIR/llmops explicitly" ;;
esac
