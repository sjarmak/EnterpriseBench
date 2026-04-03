#!/usr/bin/env bash
# Checkpoint 3: Verify agent identified affected connector configurations
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kafka/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must mention Kafka Connect task lifecycle
if grep -qiE 'put.*flush.*commit|task.*lifecycle|WorkerSinkTask.*cycle|offset.*flush' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention JDBC connector batch/transaction config
if grep -qiE 'batch\.size|jdbc.*batch|transaction.*manag|BufferedRecords' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d affected configurations"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
