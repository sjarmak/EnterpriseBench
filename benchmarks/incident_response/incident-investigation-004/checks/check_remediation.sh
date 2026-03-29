#!/usr/bin/env bash
# Checkpoint 4: Verify agent proposed correct remediation
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must mention suppressing or downgrading the warning for ErrRestartCanceled
if grep -qiE 'suppress.*warn|downgrad.*warn|not.*log.*warn|skip.*warn|info.*instead.*warn|ErrRestartCanceled.*not.*warn|ignore.*ErrRestartCanceled' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention improving the "ignoring event" log message
if grep -qiE 'ignoring.*event.*improv|better.*log.*message|descriptive.*message|received.*task.*delete|clarif.*log' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 1 ]; then
  PASSED=true
else
  PASSED=false
fi

printf '{"score": %s, "passed": %s, "reason": "Remediation quality: %d/%d key elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
