#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="${LLMOPS_GITHUB_REPOSITORY:-}"
VERSION="${LLMOPS_VERSION:-latest}"
ARCHIVE=""
CHECKSUM_FILE=""
INSTALL_BASE="${LLMOPS_INSTALL_BASE:-$HOME/.local/llm-ops}"
PUBLIC_BIN_DIR="${LLMOPS_PUBLIC_BIN_DIR:-$HOME/.local/bin}"
STATE_HOME="${LLMOPS_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/llm-ops}"
KEEP_DOWNLOAD=0
MINIMAL=0

usage() {
  cat <<'USAGE'
Usage: bootstrap-install.sh [options]

Download and verify a published LLM-Ops-Kit runtime, or install a verified
local release artifact. A Git checkout is not required.

Options:
  --version <version>         GitHub release tag or version (default: latest)
  --repository <owner/repo>   GitHub repository
  --archive <path>            Install a local release archive
  --checksum-file <path>      SHA-256 file for --archive
  --prefix <path>             Install root
  --public-bin-dir <path>     Public command directory
  --state-home <path>         State root
  --keep-download             Preserve the temporary download directory
  --minimal                   Install CLI without the Textual console
  -h, --help                  Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --repository) REPOSITORY="$2"; shift 2 ;;
    --archive) ARCHIVE="$2"; shift 2 ;;
    --checksum-file) CHECKSUM_FILE="$2"; shift 2 ;;
    --prefix) INSTALL_BASE="$2"; shift 2 ;;
    --public-bin-dir) PUBLIC_BIN_DIR="$2"; shift 2 ;;
    --state-home) STATE_HOME="$2"; shift 2 ;;
    --keep-download) KEEP_DOWNLOAD=1; shift ;;
    --minimal) MINIMAL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "bootstrap-install.sh: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$ARCHIVE" ]]; then
  [[ "$REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "bootstrap-install.sh: --repository or LLMOPS_GITHUB_REPOSITORY is required for downloads" >&2; exit 2; }
fi
command -v curl >/dev/null 2>&1 || { echo "bootstrap-install.sh: curl is required" >&2; exit 2; }
command -v shasum >/dev/null 2>&1 || { echo "bootstrap-install.sh: shasum is required" >&2; exit 2; }
command -v tar >/dev/null 2>&1 || { echo "bootstrap-install.sh: tar is required" >&2; exit 2; }

temporary="$(mktemp -d "${TMPDIR:-/tmp}/llmops-bootstrap.XXXXXX")"
cleanup() {
  status=$?
  if [[ "$KEEP_DOWNLOAD" -eq 0 ]]; then rm -rf "$temporary"; else echo "DOWNLOAD DIRECTORY: $temporary"; fi
  exit "$status"
}
trap cleanup EXIT INT TERM

if [[ -n "$ARCHIVE" ]]; then
  [[ -n "$CHECKSUM_FILE" ]] || { echo "bootstrap-install.sh: --archive requires --checksum-file" >&2; exit 2; }
  cp "$ARCHIVE" "$temporary/$(basename "$ARCHIVE")"
  cp "$CHECKSUM_FILE" "$temporary/$(basename "$CHECKSUM_FILE")"
  ARCHIVE="$temporary/$(basename "$ARCHIVE")"
  CHECKSUM_FILE="$temporary/$(basename "$CHECKSUM_FILE")"
else
  if [[ "$VERSION" == "latest" ]]; then
    redirect_url="$(curl -fsSL -o /dev/null -w '%{url_effective}' "https://github.com/$REPOSITORY/releases/latest")"
    VERSION="${redirect_url##*/}"
    [[ -n "$VERSION" ]] || { echo "bootstrap-install.sh: could not resolve the latest release" >&2; exit 2; }
  fi
  [[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { echo "bootstrap-install.sh: invalid release version" >&2; exit 2; }
  archive_name="LLM-Ops-Kit-$VERSION.tar.xz"
  base_url="https://github.com/$REPOSITORY/releases/download/$VERSION"
  ARCHIVE="$temporary/$archive_name"
  CHECKSUM_FILE="$temporary/$archive_name.sha256"
  curl -fL --retry 3 --connect-timeout 15 -o "$ARCHIVE" "$base_url/$archive_name"
  curl -fL --retry 3 --connect-timeout 15 -o "$CHECKSUM_FILE" "$base_url/$archive_name.sha256"
fi

archive_name="$(basename "$ARCHIVE")"
checksum_name="$(basename "$CHECKSUM_FILE")"
(
  cd "$temporary"
  expected="$(sed -n '1{s/[[:space:]].*//;p;}' "$checksum_name")"
  actual="$(shasum -a 256 "$archive_name" | awk '{print $1}')"
  [[ "$expected" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "bootstrap-install.sh: invalid checksum file" >&2; exit 2; }
  [[ "$actual" == "$expected" ]] || { echo "bootstrap-install.sh: archive checksum mismatch" >&2; exit 2; }
)

extract="$temporary/extracted"
mkdir -p "$extract"
tar -xJf "$ARCHIVE" -C "$extract"
installer="$(find "$extract" -type f -path '*/scripts/install-runtime.sh' -print -quit)"
[[ -n "$installer" ]] || { echo "bootstrap-install.sh: release archive is missing the installer" >&2; exit 2; }
source_root="$(cd "$(dirname "$installer")/.." && pwd)"
release_id="$(basename "$ARCHIVE" .tar.xz)"
release_id="${release_id#LLM-Ops-Kit-}"

install_args=(
  --source "$source_root"
  --prefix "$INSTALL_BASE"
  --public-bin-dir "$PUBLIC_BIN_DIR"
  --state-home "$STATE_HOME"
  --release-id "$release_id"
)
[[ "$MINIMAL" -eq 1 ]] && install_args+=(--minimal)

bash_bin="${BASH_BIN:-$(command -v bash)}"
"$bash_bin" "$installer" \
  "${install_args[@]}"
