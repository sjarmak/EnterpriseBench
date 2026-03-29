#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/discourse/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=6
if grep -qE 'reviewable_serializer' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'reviewable_claimed_topic_serializer' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'reviewable_topic_serializer' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'user_guardian' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'reviewable-item' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'client\.en\.yml|locales' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 4 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d indirect reference locations"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
