#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/discourse/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qE 'category_approval_groups_spec|migrate.*spec' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'category_posting_review_group_spec' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'category_setting_spec' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'category_spec' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d spec files"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
