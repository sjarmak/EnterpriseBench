#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause across all three repos
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify runc process execution as the deepest root cause
if grep -qiE 'process_linux\.go|libcontainer.*process|runc.*exec' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention execve or exec format error mechanism
if grep -qiE 'execve|ENOEXEC|exec.*format|format.*error' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention shebang or /bin/sh fallback as contributing factor
if grep -qiE 'shebang|/bin/sh.*fallback|missing.*shebang|kernel.*fallback' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 2 ]; then
  PASSED=true
else
  PASSED=false
fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d root cause elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
