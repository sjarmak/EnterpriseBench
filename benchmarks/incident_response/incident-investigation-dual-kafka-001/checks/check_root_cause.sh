#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause files in both repos
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kafka/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify WorkerSinkTask in Kafka Connect
if grep -qiE 'WorkerSinkTask|worker.*sink.*task' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must identify JdbcSinkTask or BufferedRecords in JDBC connector
if grep -qiE 'JdbcSinkTask|BufferedRecords|jdbc.*sink.*task' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention transaction timeout interaction
if grep -qiE 'transaction.*timeout|statement.*timeout|batch.*timeout|timeout.*interact' "$REPORT"; then
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
