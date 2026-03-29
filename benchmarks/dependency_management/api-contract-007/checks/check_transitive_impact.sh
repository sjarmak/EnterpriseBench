#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'go get.*-u|go.*mod.*tidy|dependency.*resolv' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'module.*proxy|proxy.*resolut|go.*sum' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'exclude|workaround|go mod edit' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d resolution mechanism aspects"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
