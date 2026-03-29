#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/mattermost/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qE 'model/view_test' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'storetest/view_store' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'api4/view_test' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'app/view_test' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d test files"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
