#!/usr/bin/env bash
set -euo pipefail

# Generate a sanitized daily markdown report from gateway logs.
# No raw message bodies, credentials, or tokens are included.

DATE_ARG="${1:-$(date +%F)}"
REPORT_ROOT="${2:-$HOME/projects/LLM-Ops-Kit/docs/reports}"
REPORT_FILE="${REPORT_ROOT}/${DATE_ARG}.md"
LOG_FILE="$(ls -1t /tmp/openclaw/openclaw-*.log 2>/dev/null | head -n1 || true)"

mkdir -p "${REPORT_ROOT}"

count_matches() {
  local pattern="$1"
  local file="$2"
  local count
  count="$(rg -c --no-messages "$pattern" "$file" 2>/dev/null || true)"
  if [[ -z "${count}" ]]; then
    echo "0"
  else
    echo "${count}"
  fi
}

{
  echo "# OpenClaw Sanitized Daily Report (${DATE_ARG})"
  echo
  echo "## Service Status"
  if pgrep -fl "openclaw" >/dev/null 2>&1; then
    echo "- Gateway process: running"
  else
    echo "- Gateway process: not detected"
  fi
  if [[ -n "${LOG_FILE}" ]]; then
    echo "- Active log file: \`${LOG_FILE}\`"
  else
    echo "- Active log file: not found under \`/tmp/openclaw\`"
  fi
  echo

  echo "## Error and Warning Summary"
  if [[ -n "${LOG_FILE}" && -f "${LOG_FILE}" ]]; then
    echo "- Total \`error\` lines: $(count_matches " error " "${LOG_FILE}")"
    echo "- Total \`warn\` lines: $(count_matches " warn " "${LOG_FILE}")"
    echo "- Memory-related errors: $(count_matches "memory|embedd|sqlite-vec" "${LOG_FILE}")"
    echo "- Tool read errors: $(count_matches "read failed|ENOENT|EISDIR" "${LOG_FILE}")"
  else
    echo "- No log file available for summary."
  fi
  echo

  echo "## Top Config/Reload Signals"
  if [[ -n "${LOG_FILE}" && -f "${LOG_FILE}" ]]; then
    echo "- Reload checks: $(count_matches "gateway/reload.*evaluating reload" "${LOG_FILE}")"
    echo "- Hot reload applied: $(count_matches "gateway/reload.*hot reload applied" "${LOG_FILE}")"
    echo "- Reload skipped (invalid): $(count_matches "gateway/reload.*skipped \\(invalid config\\)" "${LOG_FILE}")"
    echo "- Invalid config events: $(count_matches "Invalid config at " "${LOG_FILE}")"
  else
    echo "- No config/reload data found."
  fi
  echo

  echo "## Action Items and Risks"
  echo "- Review repeated warnings/errors and decide whether they need config, model, or skill fixes."
  echo "- Keep runtime/session/auth artifacts ignored in git; do not commit raw logs or transcripts."
  echo "- Revisit curated conversation export policy before enabling any session archival to remote."
} > "${REPORT_FILE}"

echo "Wrote sanitized report: ${REPORT_FILE}"
