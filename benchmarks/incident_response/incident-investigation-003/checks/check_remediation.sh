#!/usr/bin/env bash
# Checkpoint 4: Verify agent proposed correct remediation
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/grafana/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must mention checking iter.Error or adding error checks to parsing
if grep -qiE 'check.*iter\.Error|check.*error.*pars|error.*check.*json|return.*error|propagat.*error' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention either wrapping jsoniter or returning error instead of partial data
if grep -qiE 'wrap.*jsoniter|return.*error.*instead|stop.*partial|reject.*partial|error.*wrapper|jsonitere' "$REPORT"; then
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
