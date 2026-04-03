#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the reconciliation failure chain
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/flux2/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention stale/old status conditions from pre-upgrade
if grep -qiE 'stale.*condition|old.*condition|pre.?upgrade.*condition|in.?progress.*upgrade' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention reconciler parsing failure
if grep -qiE 'reconcil.*cannot.*pars|reconcil.*fail|cannot.*interpret|mismatch' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention not-ready status result
if grep -qiE 'not.?ready|Ready.*False|ArtifactFailed|ReconciliationFailed' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention infinite reconciliation loop
if grep -qiE 'infinite.*loop|reconcil.*loop|re.?reconcil|endless.*reconcil' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d reconciliation failure steps"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
