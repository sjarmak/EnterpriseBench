#!/usr/bin/env bash
# Checkpoint 4: Verify breakage classification
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

CONTENT=$(cat "$REPORT" | tr '[:upper:]' '[:lower:]')
FOUND=0
TOTAL=2
# Must identify compile errors
if echo "$CONTENT" | grep -qE 'compile|compilation|build.*error|undefined.*function'; then FOUND=$((FOUND + 1)); fi
# Must identify runtime behavior change (silent metadata loss)
if echo "$CONTENT" | grep -qE 'runtime|silent|behavior.*change|metadata.*lost|metadata.*drop'; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Classified %d/%d breakage types"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
