#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2
# Agent should mention ParseAcceptLanguage as the vulnerable function
if grep -qiE 'ParseAcceptLanguage|Accept.Language' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Agent should distinguish between repos that use the vulnerable function and those that don't
if grep -qiE 'not.*call|does.*not.*use|only.*import|language.*package|transform' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Function-level analysis: %d/%d criteria met"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
