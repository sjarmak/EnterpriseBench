#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the error chain
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/grafana/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention Prometheus API as source
if grep -qiE 'prometheus.*api|prometheus.*response|prometheus.*http' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention data proxy or response_limit
if grep -qiE 'data.?proxy|response.?limit|dataproxy' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the converter or prom.go
if grep -qiE 'converter|prom\.go' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention jsoniter or the JSON parsing library
if grep -qiE 'jsoniter|json.iterator|json.?iter|Iterator' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 3 ]; then
  PASSED=true
else
  PASSED=false
fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d error chain components"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
