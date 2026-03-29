#!/usr/bin/env bash
# Checkpoint 3: Verify agent finds frontend references
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/zulip/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=6
if grep -qE 'settings_org' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'settings_data' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'settings_components' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'stream_settings_ui' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'state_data' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'organization_permissions.*hbs|permissions_admin' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 4 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d frontend reference locations"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
