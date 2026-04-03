#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause file and mechanism
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/istio/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify Istio Pilot route translation code
if grep -qiE 'route\.go|v1alpha3/route|pilot.*route.*translat' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention regex engine or safe_regex configuration change
if grep -qiE 'regex.*engine|safe_regex|regex.*config.*change|re2|google.*re2' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention Envoy config_impl or router matching
if grep -qiE 'config_impl|route.*match|header.*match.*fail|header_utility' "$REPORT"; then
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
