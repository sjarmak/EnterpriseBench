#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/discourse/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qE 'category_setting_spec' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'category_spec' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'category_create_response\.json|category_update_response\.json' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d test/schema files"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
