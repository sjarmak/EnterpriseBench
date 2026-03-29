#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/sentry/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qE 'models/dashboard' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'backup/comparators' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'helpers/backups|testutils.*backups' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d backend reference locations"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
