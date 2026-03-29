#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/discourse/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2
if grep -qE 'mark_category_approval.*readonly|20260310072550' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'create_category_approval_groups|20260310072759' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d migration files"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
