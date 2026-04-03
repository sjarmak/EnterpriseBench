#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/discourse/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qE 'reviewable\.rb|models/reviewable' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'reviewable_flagged_post' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'reviewables_controller' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'reviewable_claimed_topics_controller' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d direct reference locations"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
