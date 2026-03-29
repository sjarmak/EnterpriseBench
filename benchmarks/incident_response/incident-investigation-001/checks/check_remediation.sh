#!/usr/bin/env bash
# Checkpoint 4: Verify agent proposed correct remediation
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kubernetes/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must mention returning 410 Gone or "too old" error to force relist
if grep -qiE '410.*gone|too.old.*resource|force.*relist|reject.*watch|gone.*error' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the empty cache condition or checking resourceVersion bounds
if grep -qiE 'empty.*cache|check.*resource.?version|oldest.*version|bounds.*check|version.*comparison' "$REPORT"; then
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
