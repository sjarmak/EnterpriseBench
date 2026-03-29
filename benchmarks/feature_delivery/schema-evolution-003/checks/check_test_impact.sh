#!/usr/bin/env bash
# Checkpoint 4: Verify agent identifies test files across backend + frontend
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/zulip/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=5
if grep -qE 'test_events' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'test_realm' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'dispatch\.test' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'settings_data\.test' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'settings_org\.test' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d test files"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
