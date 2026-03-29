#!/usr/bin/env bash
# Checkpoint 4: Verify agent assesses fix complexity correctly
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

CONTENT=$(cat "$REPORT" | tr '[:upper:]' '[:lower:]')
FOUND=0
TOTAL=2
# Must identify compile error as breakage type
if echo "$CONTENT" | grep -qE 'compile|build.*error|won.*compile|build.*fail'; then FOUND=$((FOUND + 1)); fi
# Must identify that deeper architectural change is needed (not just import rename)
if echo "$CONTENT" | grep -qE 'architect|rework|replac|refactor|upstream|deeper.*change'; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Classified %d/%d breakage aspects"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
