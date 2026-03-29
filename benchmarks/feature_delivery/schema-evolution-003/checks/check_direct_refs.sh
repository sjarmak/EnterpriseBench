#!/usr/bin/env bash
# Checkpoint 2: Verify agent finds backend references
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/zulip/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=5
if grep -qE 'actions/realm_settings' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'actions/create_realm' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'views/realm' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'lib/events' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'event_schema' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 4 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d backend reference locations"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
