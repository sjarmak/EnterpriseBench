#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'cel\.Program|cel.*Program.*interface' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'new.*method|added.*method|method.*added' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'v0\.10\.1|cel-go.*0\.10' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d source elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
