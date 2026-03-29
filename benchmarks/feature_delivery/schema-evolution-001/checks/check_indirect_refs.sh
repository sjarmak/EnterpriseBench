#!/usr/bin/env bash
# Checkpoint 3: Verify agent finds indirect references
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/zulip/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=6
if grep -qE 'lib/events' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'event_schema' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'import_realm' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'markdown' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'openapi.*zulip\.yaml|zulip\.yaml' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'realm_audit_log' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 4 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d indirect reference locations"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
