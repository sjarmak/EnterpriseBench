#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

CONTENT=$(cat "$REPORT" | tr '[:upper:]' '[:lower:]')
FOUND=0
TOTAL=2
# Must identify runtime fatal (not just compile error)
if echo "$CONTENT" | grep -qE 'runtime.*fatal|fatal.*runtime|reject.*request|connection.*refuse'; then FOUND=$((FOUND + 1)); fi
# Must identify phased rollout (warning → fatal → removed)
if echo "$CONTENT" | grep -qE 'warn.*fatal|phase|gradual|override|rollout'; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Classified %d/%d breakage aspects"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
