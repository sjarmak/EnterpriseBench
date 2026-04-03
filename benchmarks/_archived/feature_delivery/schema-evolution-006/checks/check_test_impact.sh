#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/discourse/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qE 'invite_spec' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'invites_controller_spec' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'create_invite_spec|system.*invite' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d spec files"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
