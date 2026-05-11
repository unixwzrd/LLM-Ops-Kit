#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -h "$SOURCE" ]]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
SOURCE_DIR_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_DIR="${LLMOPS_SOURCE_DIR:-$SOURCE_DIR_DEFAULT}"
INSTALL_BASE="${LLMOPS_INSTALL_BASE:-$HOME/.local/llm-ops}"
INSTALL_DIR="$INSTALL_BASE/current"
BIN_DIR="${BIN_DIR:-${LLMOPS_BIN_DIR:-$HOME/.local/llm-ops/bin}}"
PUBLIC_BIN_DIR="${LLMOPS_PUBLIC_BIN_DIR:-$HOME/.local/bin}"
STATE_HOME="${LLMOPS_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/llm-ops}"
STATE_FILE="${LLMOPS_STATE_FILE:-$STATE_HOME/runtime-state.env}"
VENV_PATH="${LLMOPS_RUNTIME_VENV_PATH:-}"
INSTALL_SECRETS_KIT=0
SECRETS_KIT_SOURCE="${LLMOPS_SECRETS_KIT_SOURCE:-git+https://github.com/unixwzrd/Secrets-Kit.git}"
PYTHON_PACKAGES="${LLMOPS_RUNTIME_VENV_PACKAGES:-jinja2}"
NO_LINKS=0
UPDATE_SHELL_PROFILE=1
SHELL_PROFILE="${LLMOPS_SHELL_PROFILE:-}"

expand_path() {
  local raw="$1"
  case "$raw" in
    "~") printf '%s\n' "$HOME" ;;
    "~/"*) printf '%s/%s\n' "$HOME" "${raw#\~/}" ;;
    *) printf '%s\n' "$raw" ;;
  esac
}

ensure_runtime_venv() {
  local venv="$1"
  local python_bin
  [[ -n "$venv" ]] || return 0

  venv="$(expand_path "$venv")"
  python_bin="$venv/bin/python"
  if [[ ! -x "$python_bin" ]]; then
    echo "Creating runtime venv at: $venv"
    python3 -m venv "$venv"
  fi

  if [[ -n "${PYTHON_PACKAGES// }" ]]; then
    echo "Installing runtime Python packages into: $venv"
    "$python_bin" -m pip install ${PYTHON_PACKAGES}
  fi

  if [[ "$INSTALL_SECRETS_KIT" -eq 1 ]]; then
    echo "Installing Secrets-Kit into runtime venv from: $SECRETS_KIT_SOURCE"
    "$python_bin" -m pip install "$SECRETS_KIT_SOURCE"
  fi

  VENV_PATH="$venv"
}

default_shell_profile() {
  if [[ -n "$SHELL_PROFILE" ]]; then
    printf '%s\n' "$SHELL_PROFILE"
    return 0
  fi
  case "${SHELL:-}" in
    */zsh) printf '%s/.zprofile\n' "$HOME" ;;
    *)
      case "$(uname -s 2>/dev/null || printf unknown)" in
        Darwin) printf '%s/.bash_profile\n' "$HOME" ;;
        *) printf '%s/.bashrc\n' "$HOME" ;;
      esac
      ;;
  esac
}

install_public_launcher() {
  local launcher_src="$1"
  mkdir -p "$PUBLIC_BIN_DIR"
  ln -sfn "$launcher_src" "$PUBLIC_BIN_DIR/llmops"
  echo "LINKED_PUBLIC: $PUBLIC_BIN_DIR/llmops -> $launcher_src"
}

ensure_shell_profile_path() {
  local profile_file="$1"
  local public_bin="$2"
  local tmp_file
  [[ "$UPDATE_SHELL_PROFILE" -eq 1 ]] || return 0
  mkdir -p "$(dirname "$profile_file")"
  touch "$profile_file"
  tmp_file="${profile_file}.tmp.$$"
  awk '
    $0 == "# >>> llm-ops path >>>" { skip=1; next }
    $0 == "# <<< llm-ops path <<<" { skip=0; next }
    skip == 1 { next }
    { print }
  ' "$profile_file" > "$tmp_file"
  {
    cat "$tmp_file"
    printf '\n# >>> llm-ops path >>>\n'
    printf 'export PATH="%s:$PATH"\n' "$public_bin"
    printf '# <<< llm-ops path <<<\n'
  } > "$profile_file"
  rm -f "$tmp_file"
  echo "UPDATED_SHELL_PROFILE: $profile_file"
}

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --source <path>      Source repo directory (default: $SOURCE_DIR_DEFAULT)
  --prefix <path>      Install base dir (default: ~/.local/llm-ops)
  --bin-dir <path>     Managed runtime bin dir (default: ~/.local/llm-ops/bin)
  --public-bin-dir <path>  Public launcher dir (default: ~/.local/bin)
  --state-file <path>  Runtime state file (default: ~/.local/state/llm-ops/runtime-state.env)
  --venv-path <path>   Optional runtime Python virtualenv path
  --install-secrets-kit  Install Secrets-Kit into the runtime venv
  --secrets-kit-source <spec>  pip install source for Secrets-Kit
  --no-links           Install files only; skip link deploy/verify
  --no-shell-profile   Do not update shell startup files
  --shell-profile <path>  Shell startup file to update (default: detected)
  -h, --help           Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE_DIR="$2"; shift 2 ;;
    --prefix) INSTALL_BASE="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --public-bin-dir) PUBLIC_BIN_DIR="$2"; shift 2 ;;
    --state-file) STATE_FILE="$2"; shift 2 ;;
    --venv-path) VENV_PATH="$2"; shift 2 ;;
    --install-secrets-kit) INSTALL_SECRETS_KIT=1; shift ;;
    --secrets-kit-source) SECRETS_KIT_SOURCE="$2"; shift 2 ;;
    --no-links) NO_LINKS=1; shift ;;
    --no-shell-profile) UPDATE_SHELL_PROFILE=0; shift ;;
    --shell-profile) SHELL_PROFILE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

SOURCE_DIR="$(expand_path "$SOURCE_DIR")"
INSTALL_BASE="$(expand_path "$INSTALL_BASE")"
BIN_DIR="$(expand_path "$BIN_DIR")"
PUBLIC_BIN_DIR="$(expand_path "$PUBLIC_BIN_DIR")"
STATE_FILE="$(expand_path "$STATE_FILE")"
if [[ -n "$SHELL_PROFILE" ]]; then
  SHELL_PROFILE="$(expand_path "$SHELL_PROFILE")"
fi
if [[ -n "$VENV_PATH" ]]; then
  VENV_PATH="$(expand_path "$VENV_PATH")"
fi

INSTALL_DIR="$INSTALL_BASE/current"
STAGING_DIR="$INSTALL_BASE/.staging.$$"
BACKUP_DIR="$INSTALL_BASE/backups/$(date +%Y%m%d-%H%M%S)"

[[ -d "$SOURCE_DIR/scripts" ]] || { echo "Missing source scripts dir: $SOURCE_DIR/scripts" >&2; exit 1; }
[[ -d "$SOURCE_DIR/bin" ]] || { echo "Missing source bin dir: $SOURCE_DIR/bin" >&2; exit 1; }
[[ -x "$SOURCE_DIR/scripts/deploy-runtime-links.sh" ]] || {
  echo "Missing deploy script in source: $SOURCE_DIR/scripts/deploy-runtime-links.sh" >&2
  exit 1
}

mkdir -p "$INSTALL_BASE" "$BIN_DIR" "$PUBLIC_BIN_DIR"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

echo "Installing runtime payload from: $SOURCE_DIR"
rsync -a --delete "$SOURCE_DIR/scripts/" "$STAGING_DIR/scripts/"
rsync -a --delete "$SOURCE_DIR/bin/" "$STAGING_DIR/bin/"

if [[ -d "$INSTALL_DIR" ]]; then
  mkdir -p "$(dirname "$BACKUP_DIR")"
  mv "$INSTALL_DIR" "$BACKUP_DIR"
  echo "Backed up previous runtime to: $BACKUP_DIR"
fi

mv "$STAGING_DIR" "$INSTALL_DIR"
echo "Installed runtime to: $INSTALL_DIR"

ensure_runtime_venv "$VENV_PATH"

if [[ "$NO_LINKS" -eq 0 ]]; then
  pushd "$INSTALL_DIR/scripts" >/dev/null
  ./generate-manifest
  BIN_DIR="$BIN_DIR" RUNTIME_DIR="$INSTALL_DIR" ./deploy-runtime-links.sh --replace-managed-links
  BIN_DIR="$BIN_DIR" RUNTIME_DIR="$INSTALL_DIR" ./verify-runtime-links.sh
  popd >/dev/null
  install_public_launcher "$INSTALL_DIR/scripts/llmops"
  ensure_shell_profile_path "$(default_shell_profile)" "$PUBLIC_BIN_DIR"
fi

if [[ -f "$INSTALL_DIR/scripts/lib/common.sh" ]]; then
  # shellcheck disable=SC1090
  . "$INSTALL_DIR/scripts/lib/common.sh"
  prune_runtime_backups
fi

mkdir -p "$(dirname "$STATE_FILE")"
cat > "$STATE_FILE" <<EOF
LLMOPS_INSTALL_MODE=installed
LLMOPS_INSTALL_BASE=$INSTALL_BASE
LLMOPS_INSTALL_DIR=$INSTALL_DIR
LLMOPS_BIN_DIR=$BIN_DIR
LLMOPS_PUBLIC_BIN_DIR=$PUBLIC_BIN_DIR
LLMOPS_SOURCE_DIR=$SOURCE_DIR
LLMOPS_RUNTIME_VENV_PATH=$VENV_PATH
LLMOPS_UPDATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
echo "WROTE_STATE: $STATE_FILE"

echo "Install complete."
