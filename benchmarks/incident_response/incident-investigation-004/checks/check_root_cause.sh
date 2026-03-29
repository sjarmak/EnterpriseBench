#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause file and mechanism
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify monitor.go or handleContainerExit
if grep -qiE 'monitor\.go|handleContainerExit|handle.*container.*exit' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention ErrRestartCanceled or restart canceled error
if grep -qiE 'ErrRestartCanceled|restart.?canceled|restart.*cancel' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention ShouldRestart being called during shutdown
if grep -qiE 'ShouldRestart|should.*restart' "$REPORT"; then
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
