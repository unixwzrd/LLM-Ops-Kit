#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:?usage: host_install_acceptance.sh <source-dir> <acceptance-root>}"
ACCEPTANCE_ROOT="${2:?usage: host_install_acceptance.sh <source-dir> <acceptance-root>}"

INSTALL="$ACCEPTANCE_ROOT/install"
PUBLIC_BIN="$ACCEPTANCE_ROOT/public-bin"
CONFIG="$ACCEPTANCE_ROOT/config"
DATA="$ACCEPTANCE_ROOT/data"
STATE="$ACCEPTANCE_ROOT/state"
CACHE="$ACCEPTANCE_ROOT/cache"
LEGACY="$ACCEPTANCE_ROOT/legacy"
MIGRATED_CONFIG="$ACCEPTANCE_ROOT/migrated-config"
EVIDENCE="$ACCEPTANCE_ROOT/evidence"

mkdir -p "$EVIDENCE"
exec > >(tee "$EVIDENCE/acceptance.log") 2>&1

export LLMOPS_HOME="$INSTALL"
export LLMOPS_BIN_DIR="$INSTALL/bin"
export LLMOPS_CONFIG_HOME="$CONFIG"
export LLMOPS_DATA_HOME="$DATA"
export LLMOPS_STATE_HOME="$STATE"
export LLMOPS_CACHE_HOME="$CACHE"
BASH_BIN="${BASH_BIN:-$(command -v bash)}"

installer=(
  "$BASH_BIN" "$SOURCE_DIR/scripts/install-runtime.sh"
  --source "$SOURCE_DIR"
  --prefix "$INSTALL"
  --public-bin-dir "$PUBLIC_BIN"
  --state-home "$STATE"
)
uninstaller=(
  "$BASH_BIN" "$SOURCE_DIR/scripts/uninstall-runtime.sh"
  --prefix "$INSTALL"
  --public-bin-dir "$PUBLIC_BIN"
  --config-home "$CONFIG"
  --data-home "$DATA"
  --state-home "$STATE"
  --cache-home "$CACHE"
)

assert_link_target() {
  local link="$1" expected="$2"
  [[ "$(readlink "$link")" == "$expected" ]] || {
    echo "expected $link -> $expected, found $(readlink "$link")" >&2
    return 1
  }
}

echo "==> fresh install"
"${installer[@]}" --release-id acceptance-1
assert_link_target "$INSTALL/current" "$INSTALL/releases/acceptance-1"
[[ ! -e "$INSTALL/previous" ]]
"$PUBLIC_BIN/llmops" init --preset single-host

"$INSTALL/current/app/bin/python" "$SOURCE_DIR/scripts/tests/host_acceptance_helper.py" \
  configure-inventory "$CONFIG/inventory.json" "$INSTALL" "$PUBLIC_BIN"

"$PUBLIC_BIN/llmops" doctor --json > "$EVIDENCE/doctor.json"
"$PUBLIC_BIN/llmops" config show --json > "$EVIDENCE/config.json"
"$PUBLIC_BIN/llmops" plan --json > "$EVIDENCE/plan.json"

echo "==> idempotent repair"
"${installer[@]}" --repair
"${installer[@]}" --repair

echo "==> upgrade and rollback"
"${installer[@]}" --release-id acceptance-2
assert_link_target "$INSTALL/current" "$INSTALL/releases/acceptance-2"
assert_link_target "$INSTALL/previous" "$INSTALL/releases/acceptance-1"
"$PUBLIC_BIN/llmops" rollback --config-home "$CONFIG" --json > "$EVIDENCE/rollback-1.json"
assert_link_target "$INSTALL/current" "$INSTALL/releases/acceptance-1"
assert_link_target "$INSTALL/previous" "$INSTALL/releases/acceptance-2"
"$PUBLIC_BIN/llmops" rollback --config-home "$CONFIG" --json > "$EVIDENCE/rollback-2.json"
assert_link_target "$INSTALL/current" "$INSTALL/releases/acceptance-2"

echo "==> preserving uninstall"
mkdir -p "$DATA" "$CACHE"
printf 'preserve\n' > "$DATA/sentinel"
printf 'preserve\n' > "$CACHE/sentinel"
"${uninstaller[@]}"
[[ ! -e "$INSTALL" && ! -e "$PUBLIC_BIN/llmops" ]]
[[ -f "$CONFIG/config.json" && -f "$DATA/sentinel" && -f "$CACHE/sentinel" ]]

echo "==> reinstall"
"${installer[@]}" --release-id acceptance-3
"$PUBLIC_BIN/llmops" doctor --json > "$EVIDENCE/doctor-reinstall.json"

echo "==> one-way migration"
mkdir -p "$LEGACY/config"
printf 'MODEL_HOST=127.0.0.1\nMODEL_PORT=11434\n' > "$LEGACY/config.env"
printf 'MODEL_NAME=test-model\nMODEL_PATH=/tmp/test-model.gguf\n' > "$LEGACY/config/test-model.env"
LLMOPS_CONFIG_HOME="$MIGRATED_CONFIG" "$PUBLIC_BIN/llmops" migrate-config --legacy-home "$LEGACY" --dry-run --json > "$EVIDENCE/migration-dry-run.json"
LLMOPS_CONFIG_HOME="$MIGRATED_CONFIG" "$PUBLIC_BIN/llmops" migrate-config --legacy-home "$LEGACY" --json > "$EVIDENCE/migration.json"
LLMOPS_CONFIG_HOME="$MIGRATED_CONFIG" "$PUBLIC_BIN/llmops" migrate-config --legacy-home "$LEGACY" --json > "$EVIDENCE/migration-noop.json"
"$INSTALL/current/app/bin/python" "$SOURCE_DIR/scripts/tests/host_acceptance_helper.py" \
  tree-digest "$MIGRATED_CONFIG" "$EVIDENCE/migrated-before.sha256"
printf 'CHANGED_AFTER_MIGRATION=yes\n' >> "$LEGACY/config.env"
if LLMOPS_CONFIG_HOME="$MIGRATED_CONFIG" "$PUBLIC_BIN/llmops" migrate-config --legacy-home "$LEGACY" --json > "$EVIDENCE/migration-refusal.json" 2>&1; then
  echo "changed migration source was not refused" >&2
  exit 1
fi
"$INSTALL/current/app/bin/python" "$SOURCE_DIR/scripts/tests/host_acceptance_helper.py" \
  tree-digest "$MIGRATED_CONFIG" "$EVIDENCE/migrated-after.sha256"
cmp "$EVIDENCE/migrated-before.sha256" "$EVIDENCE/migrated-after.sha256"

echo "==> purge"
"${uninstaller[@]}" --purge
for path in "$INSTALL" "$CONFIG" "$DATA" "$STATE" "$CACHE"; do
  [[ ! -e "$path" ]] || { echo "purge left managed path: $path" >&2; exit 1; }
done

printf 'PASS\n' > "$EVIDENCE/result"
echo "PASS: host install lifecycle acceptance"
