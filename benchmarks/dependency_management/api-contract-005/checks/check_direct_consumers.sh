#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qiE 'status\.Details|Details\(\)' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'WithDetails|WithDetails\(\)' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'status_ext_test|status.*test' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'encoding/proto|proto\.go' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d consumer areas"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
