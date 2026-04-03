#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the error chain from VirtualService to 503
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/istio/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention VirtualService as entry point
if grep -qiE 'virtualservice|virtual.?service' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention Pilot translation step
if grep -qiE 'pilot.*translat|route.*translat|istio.*generat.*envoy' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention Envoy route config or filter chain
if grep -qiE 'envoy.*route.*config|filter.*chain|route.*match' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention 503 response
if grep -qiE '503|upstream.*connect|no.*healthy.*upstream' "$REPORT"; then
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
