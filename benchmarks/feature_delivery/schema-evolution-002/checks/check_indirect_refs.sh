#!/usr/bin/env bash
# Checkpoint 3: Verify agent finds indirect references
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/zulip/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qE 'worker.*deferred_work|deferred_work' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'management/commands/export' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'lib/export' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d indirect reference locations"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
