#!/usr/bin/env bash
# Checkpoint 3: Verify agent listed affected components/services
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

# Must mention controllers or informers or client-go
if grep -qiE 'controller|informer|client.go' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention etcd or storage
if grep -qiE 'etcd|storage' "$REPORT"; then
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
