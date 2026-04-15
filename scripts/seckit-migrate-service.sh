#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  seckit-migrate-service.sh --from-service openclaw --from-account miafour \
    --to-service hermes --to-account default [--names NAME1,NAME2]

This copies secrets between Seckit service namespaces using a local export
and dotenv import. Values are never written to disk outside a temporary file.

Optional SSH example (not executed here):
  ssh host 'seckit export --format shell --service openclaw --account miafour --all' | \
    seckit import env --dotenv /dev/stdin --service hermes --account default --yes
EOF
}

from_service=""
from_account=""
to_service=""
to_account=""
names=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-service) from_service="$2"; shift 2 ;;
    --from-account) from_account="$2"; shift 2 ;;
    --to-service) to_service="$2"; shift 2 ;;
    --to-account) to_account="$2"; shift 2 ;;
    --names) names="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

[[ -n "$from_service" && -n "$from_account" && -n "$to_service" && -n "$to_account" ]] || { usage; exit 2; }

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

if [[ -n "$names" ]]; then
  seckit export --format shell --service "$from_service" --account "$from_account" --names "$names" > "$tmp"
else
  seckit export --format shell --service "$from_service" --account "$from_account" --all > "$tmp"
fi

seckit import env --dotenv "$tmp" --service "$to_service" --account "$to_account" --allow-overwrite --yes
