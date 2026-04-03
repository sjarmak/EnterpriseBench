#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause files in both repos
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/alertmanager/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify inhibitor.go in Alertmanager
if grep -qiE 'inhibitor\.go|inhibit/inhibitor|inhibition.*match' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must identify rules/manager.go in Prometheus
if grep -qiE 'rules/manager\.go|rule.*manager|recording.*rule.*evaluat' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention label drop or aggregation causing perpetual alert
if grep -qiE 'label.*drop|label.*mismatch|aggregat.*drop|always.*evaluat|perpetual.*fir' "$REPORT"; then
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
