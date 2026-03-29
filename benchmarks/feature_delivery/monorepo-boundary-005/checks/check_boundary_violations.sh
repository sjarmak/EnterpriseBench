#!/usr/bin/env bash
# Checkpoint 3: Verify boundary violation identification
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/pnpm/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qE 'constants/src/index' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'dependency-path/src/index' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'lockfile-file/src/write' "$REPORT"; then FOUND=$((FOUND + 1)); fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d boundary violation locations"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
