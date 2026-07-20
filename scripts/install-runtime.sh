#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${LLMOPS_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTALL_BASE="${LLMOPS_INSTALL_BASE:-$HOME/.local/llm-ops}"
PUBLIC_BIN_DIR="${LLMOPS_PUBLIC_BIN_DIR:-$HOME/.local/bin}"
STATE_HOME="${LLMOPS_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/llm-ops}"
RELEASE_ID=""
REPAIR=0
ROLLBACK=0
MINIMAL=0
PYTHON_VERSION="${LLMOPS_PYTHON_VERSION:-3.12}"
UV_VERSION="${LLMOPS_UV_VERSION:-0.11.19}"

RUNTIME_COMMANDS=(modelctl model-proxy tts-bridge tts runtime-maintenance)

usage() {
  cat <<'USAGE'
Usage: install-runtime.sh [options]

Options:
  --source <path>          Extracted release root
  --prefix <path>          Install root (default: ~/.local/llm-ops)
  --public-bin-dir <path>  Public command directory (default: ~/.local/bin)
  --state-home <path>      State root (default: ~/.local/state/llm-ops)
  --release-id <id>        Explicit immutable release ID
  --minimal                Install the CLI without Textual
  --repair                 Rebuild links and verify the active environment
  --rollback               Exchange current and previous releases
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

replace_link() {
  local source="$1" destination="$2" temporary="${2}.new.$$"
  ln -s "$source" "$temporary"
  if ! mv -fh "$temporary" "$destination" 2>/dev/null; then
    rm -f "$destination"
    mv -f "$temporary" "$destination"
  fi
}

download_uv() {
  local destination="$1" architecture target base archive expected actual temporary
  architecture="$(uname -m)"
  case "$architecture" in
    arm64) target="aarch64-apple-darwin" ;;
    x86_64) target="x86_64-apple-darwin" ;;
    *) echo "install-runtime.sh: unsupported macOS architecture: $architecture" >&2; return 2 ;;
  esac
  command -v curl >/dev/null 2>&1 || { echo "install-runtime.sh: curl is required to bootstrap uv" >&2; return 2; }
  temporary="$(mktemp -d "${TMPDIR:-/tmp}/llmops-uv.XXXXXX")"
  base="https://github.com/astral-sh/uv/releases/download/$UV_VERSION"
  archive="uv-$target.tar.gz"
  curl -fL --retry 3 "$base/$archive" -o "$temporary/$archive"
  curl -fL --retry 3 "$base/sha256.sum" -o "$temporary/sha256.sum"
  expected="$(awk -v name="$archive" '$2 == name || $2 == "*" name {print $1; exit}' "$temporary/sha256.sum")"
  [[ "$expected" =~ ^[0-9a-fA-F]{64}$ ]] || { rm -rf "$temporary"; echo "install-runtime.sh: uv checksum was not published" >&2; return 2; }
  actual="$(shasum -a 256 "$temporary/$archive" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || { rm -rf "$temporary"; echo "install-runtime.sh: uv checksum mismatch" >&2; return 2; }
  mkdir -p "$destination"
  tar -xzf "$temporary/$archive" -C "$temporary"
  cp "$temporary/uv-$target/uv" "$destination/uv"
  chmod 755 "$destination/uv"
  rm -rf "$temporary"
}

resolve_uv() {
  if [[ -n "${LLMOPS_UV_BIN:-}" ]]; then
    [[ -x "$LLMOPS_UV_BIN" ]] || { echo "install-runtime.sh: configured uv is not executable: $LLMOPS_UV_BIN" >&2; return 2; }
    printf '%s\n' "$LLMOPS_UV_BIN"
    return
  fi
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return
  fi
  local managed="$INSTALL_BASE/bootstrap/uv"
  [[ -x "$managed" ]] || download_uv "$INSTALL_BASE/bootstrap"
  printf '%s\n' "$managed"
}

link_runtime() {
  local root="$1" name wrapper
  mkdir -p "$INSTALL_BASE/bin" "$PUBLIC_BIN_DIR"
  wrapper="$INSTALL_BASE/bin/llmops"
  printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' \
    "export LLMOPS_HOME=\"$INSTALL_BASE\"" \
    "if [[ -z \"\${LLMOPS_CONFIG_HOME:-}\" && -L \"$INSTALL_BASE/current-config\" ]]; then export LLMOPS_CONFIG_HOME=\"$INSTALL_BASE/current-config\"; fi" \
    "exec \"$INSTALL_BASE/current/app/bin/llmops\" \"\$@\"" > "$wrapper"
  chmod 755 "$wrapper"
  ln -sfn "$wrapper" "$PUBLIC_BIN_DIR/llmops"
  for name in "${RUNTIME_COMMANDS[@]}"; do
    [[ -x "$root/scripts/$name" ]] || continue
    wrapper="$root/bin/$name"
    mkdir -p "$root/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' \
      "export LLMOPS_PYTHON_BIN=\"$root/app/bin/python\"" \
      "exec \"$root/scripts/$name\" \"\$@\"" > "$wrapper"
    chmod 755 "$wrapper"
    ln -sfn "$root/bin/$name" "$INSTALL_BASE/bin/$name"
  done
}

link_pre_beta_runtime() {
  local root="$1" name
  [[ -x "$root/scripts/llmops" ]] || { echo "install-runtime.sh: prior release has no usable llmops command: $root" >&2; return 2; }
  mkdir -p "$INSTALL_BASE/bin" "$PUBLIC_BIN_DIR"
  ln -sfn "$root/scripts/llmops" "$PUBLIC_BIN_DIR/llmops"
  for name in "${RUNTIME_COMMANDS[@]}"; do
    [[ -x "$root/scripts/$name" ]] || continue
    ln -sfn "$root/scripts/$name" "$INSTALL_BASE/bin/$name"
  done
}

write_state() {
  local root="$1" release="$2" python_bin="${3:-$1/app/bin/python}"
  "$python_bin" -m llmops_kit.llmops_install_state \
    "$STATE_HOME/install.json" "$INSTALL_BASE" "$PUBLIC_BIN_DIR" "$release"
  "$python_bin" -m llmops_kit.llmops_install_state \
    "$INSTALL_BASE/install.json" "$INSTALL_BASE" "$PUBLIC_BIN_DIR" "$release"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE_DIR="$2"; shift 2 ;;
    --prefix) INSTALL_BASE="$2"; shift 2 ;;
    --public-bin-dir) PUBLIC_BIN_DIR="$2"; shift 2 ;;
    --state-home) STATE_HOME="$2"; shift 2 ;;
    --release-id) RELEASE_ID="$2"; shift 2 ;;
    --minimal) MINIMAL=1; shift ;;
    --repair) REPAIR=1; shift ;;
    --rollback) ROLLBACK=1; shift ;;
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

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "install-runtime.sh: this beta supports macOS only" >&2
  exit 2
fi

if [[ "$ROLLBACK" -eq 1 ]]; then
  [[ -L "$CURRENT" && -L "$PREVIOUS" ]] || { echo "install-runtime.sh: current and previous releases are required" >&2; exit 2; }
  current_target="$(readlink "$CURRENT")"
  previous_target="$(readlink "$PREVIOUS")"
  if [[ ! -x "$previous_target/app/bin/llmops" && ! -x "$previous_target/scripts/llmops" ]]; then
    echo "install-runtime.sh: previous release is incomplete" >&2
    exit 2
  fi
  replace_link "$previous_target" "$CURRENT"
  replace_link "$current_target" "$PREVIOUS"
  if [[ -x "$CURRENT/app/bin/llmops" ]]; then
    link_runtime "$CURRENT"
    write_state "$CURRENT" "$previous_target"
  else
    link_pre_beta_runtime "$CURRENT"
    write_state "$CURRENT" "$previous_target" "$PREVIOUS/app/bin/python"
  fi
  echo "ROLLED BACK: $previous_target"
  exit 0
fi

if [[ "$REPAIR" -eq 1 ]]; then
  [[ -L "$CURRENT" ]] || { echo "install-runtime.sh: no active installation to repair" >&2; exit 2; }
  active="$(readlink "$CURRENT")"
  [[ -x "$active/app/bin/llmops" ]] || { echo "install-runtime.sh: active application environment is incomplete: $active" >&2; exit 2; }
  "$active/app/bin/llmops" adapter list --json >/dev/null
  link_runtime "$CURRENT"
  write_state "$CURRENT" "$active"
  echo "REPAIRED: $active"
  exit 0
fi

[[ "$(uname -s)" == "Darwin" ]] || { echo "install-runtime.sh: this beta supports macOS only" >&2; exit 2; }
[[ -d "$SOURCE_DIR/wheelhouse" && -d "$SOURCE_DIR/scripts" ]] || { echo "install-runtime.sh: release wheelhouse or runtime resources are missing" >&2; exit 2; }
wheel="$(find "$SOURCE_DIR/wheelhouse" -maxdepth 1 -name 'llm_ops_kit-*.whl' -print -quit)"
[[ -n "$wheel" ]] || { echo "install-runtime.sh: LLM-Ops-Kit wheel is missing" >&2; exit 2; }

if [[ -z "$RELEASE_ID" ]]; then
  RELEASE_ID="$(basename "$wheel" | sed -E 's/^llm_ops_kit-([^ -]+)-.*/\1/')"
fi
[[ "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "install-runtime.sh: invalid release ID" >&2; exit 2; }

release="$INSTALL_BASE/releases/$RELEASE_ID"
staging="$release"
old=""
previous_old=""
previous_existed=0
release_created=0
switched=0
config_revision_created=0
current_config_created=0

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
    [[ "$release_created" -eq 1 ]] && rm -rf "$release"
    [[ "$current_config_created" -eq 1 ]] && rm -f "$INSTALL_BASE/current-config"
    [[ "$config_revision_created" -eq 1 ]] && rm -rf "$config_revision"
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

[[ ! -e "$release" ]] || { echo "install-runtime.sh: release already exists: $release" >&2; exit 2; }
mkdir -p "$staging" "$INSTALL_BASE/releases" "$INSTALL_BASE/python" "$STATE_HOME"
release_created=1
uv_bin="$(resolve_uv)"
UV_PYTHON_INSTALL_DIR="$INSTALL_BASE/python" "$uv_bin" python install "$PYTHON_VERSION" --no-bin --compile-bytecode
managed_python="$(UV_PYTHON_INSTALL_DIR="$INSTALL_BASE/python" "$uv_bin" python find "$PYTHON_VERSION" --managed-python)"
"$uv_bin" venv --python "$managed_python" --no-python-downloads "$staging/app"
requirement="llm-ops-kit"
[[ "$MINIMAL" -eq 1 ]] || requirement="llm-ops-kit[tui]"
"$uv_bin" pip install --python "$staging/app/bin/python" --offline --no-index --find-links "$SOURCE_DIR/wheelhouse" "$requirement"

mkdir -p "$staging/scripts"
rsync -a --delete --exclude tests --exclude lib --exclude __pycache__ --exclude '*.pyc' \
  --exclude bootstrap-install.sh --exclude build-release.py --exclude precheck \
  "$SOURCE_DIR/scripts/" "$staging/scripts/"
mkdir -p "$staging/scripts/lib"
cp "$SOURCE_DIR/scripts/lib/common.sh" "$staging/scripts/lib/common.sh"
for metadata in RELEASE.json release-manifest.json; do
  [[ -f "$SOURCE_DIR/$metadata" ]] && cp "$SOURCE_DIR/$metadata" "$staging/$metadata"
done
if [[ -L "$CURRENT" && -d "$CURRENT/config" ]]; then
  cp -a "$CURRENT/config" "$staging/config"
fi
[[ -x "$staging/app/bin/llmops" ]] || { echo "install-runtime.sh: application installation is incomplete" >&2; exit 2; }
"$staging/app/bin/llmops" --help >/dev/null
if [[ -d "$staging/config" && ! -L "$INSTALL_BASE/current-config" ]]; then
  config_hash="$(LLMOPS_CONFIG_HOME="$staging/config" "$staging/app/bin/llmops" config hash | awk -F= '$1 == "config_hash" {print $2}')"
  [[ "$config_hash" =~ ^[0-9a-f]{64}$ ]] || { echo "install-runtime.sh: copied configuration failed verification" >&2; exit 2; }
  config_revision="$INSTALL_BASE/config-revisions/$config_hash"
  mkdir -p "$INSTALL_BASE/config-revisions"
  if [[ ! -e "$config_revision" ]]; then
    cp -a "$staging/config" "$config_revision"
    config_revision_created=1
  fi
  replace_link "$config_revision" "$INSTALL_BASE/current-config"
  current_config_created=1
  printf '%s\n' "$config_hash" > "$INSTALL_BASE/config-revisions/.last-sync"
fi
[[ -L "$CURRENT" ]] && old="$(readlink "$CURRENT")"
if [[ -L "$PREVIOUS" ]]; then previous_old="$(readlink "$PREVIOUS")"; previous_existed=1; fi
[[ -n "$old" ]] && replace_link "$old" "$PREVIOUS"
switched=1
replace_link "$release" "$CURRENT"
link_runtime "$CURRENT"
write_state "$CURRENT" "$release"
trap - EXIT INT TERM
echo "INSTALLED: $release"
echo "CURRENT: $(readlink "$CURRENT")"
[[ -L "$PREVIOUS" ]] && echo "PREVIOUS: $(readlink "$PREVIOUS")"
case ":$PATH:" in *":$PUBLIC_BIN_DIR:"*) ;; *) echo "PATH NOTICE: add $PUBLIC_BIN_DIR to PATH or invoke $PUBLIC_BIN_DIR/llmops explicitly" ;; esac
