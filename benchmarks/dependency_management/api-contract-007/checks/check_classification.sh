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
if echo "$CONTENT" | grep -qE 'empty.*go|empty.*import|backward.*compat.*import'; then FOUND=$((FOUND + 1)); fi
if echo "$CONTENT" | grep -qE 'v0\.13\.2|version.*broke|version.*break'; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Classified %d/%d fix aspects"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
