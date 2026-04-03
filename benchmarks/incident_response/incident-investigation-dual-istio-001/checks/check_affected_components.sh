#!/usr/bin/env bash
# Checkpoint 3: Verify agent identified affected service mesh components
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/istio/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must mention Pilot route translation as affected
if grep -qiE 'pilot|istiod|route.*translat' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention regex-based VirtualServices as affected pattern
if grep -qiE 'regex.*header|regex.*match|virtualservice.*regex' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d affected components"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
