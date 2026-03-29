#!/usr/bin/env bash
# Checkpoint 3: Verify agent listed affected services
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kubernetes/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must mention apiserver
if grep -qiE 'api.?server|kube-apiserver' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention client-go or informers or controllers
if grep -qiE 'client.go|informer|controller' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention namespace-scoped watches or filtered watches
if grep -qiE 'namespace.*watch|filtered.*watch|label.*watch|scoped.*watch' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d affected services"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
