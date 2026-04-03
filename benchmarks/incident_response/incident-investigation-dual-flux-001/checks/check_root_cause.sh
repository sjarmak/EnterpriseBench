#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause in both repos
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/flux2/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify Flux reconciler condition parsing
if grep -qiE 'helmrelease_reconciler|reconcil.*condition|reconcil.*status|reconcil.*pars' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must identify helm-controller status writer
if grep -qiE 'helmrelease\.go|helm.?controller.*status|status.*condition.*writ' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention old vs new condition format mismatch
if grep -qiE 'old.*format|new.*format|condition.*format|status.*condition.*API|stale.*condition' "$REPORT"; then
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
