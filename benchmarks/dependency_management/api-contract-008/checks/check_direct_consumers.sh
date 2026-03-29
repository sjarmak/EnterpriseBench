#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'engine_test\.go|engine.*test' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'security/authorization|authorization.*engine' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'mock|fake|stub' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d consumer elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
