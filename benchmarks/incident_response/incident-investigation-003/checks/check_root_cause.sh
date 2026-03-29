#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause file and mechanism
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/grafana/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify prom.go or the converter as root cause
if grep -qiE 'prom\.go|converter/prom|util/converter' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention jsoniter error not being checked
if grep -qiE 'iter\.Error|json.?iter.*error|error.*not.*check|unchecked.*error|silent.*fail' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention truncation or response_limit as trigger
if grep -qiE 'truncat|response.?limit|malformed.*json|partial.*json' "$REPORT"; then
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
