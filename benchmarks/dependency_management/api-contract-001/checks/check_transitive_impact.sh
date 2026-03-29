#!/usr/bin/env bash
# Checkpoint 3: Verify agent identified metadata forwarding patterns
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# Must identify interceptor as critical forwarding point
if grep -qiE 'interceptor|middleware' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must identify metadata forwarding/copying pattern
if grep -qiE 'forward|propagat|copy.*metadata|metadata.*copy' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must identify auth token forwarding as affected
if grep -qiE 'auth.*token|token.*forward|credential' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d transitive impact patterns"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
