#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the error chain from batch to task failure
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kafka/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention large batch as trigger
if grep -qiE 'large.*batch|batch.*size|batch.*5000' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention JDBC transaction duration
if grep -qiE 'jdbc.*transaction|database.*transaction|transaction.*duration' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention database timeout causing rollback
if grep -qiE 'statement.*timeout|db.*timeout|rollback|SQLException' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention task failure and restart loop
if grep -qiE 'task.*fail|restart.*loop|ConnectException|FAILED.*state' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d error chain steps"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
