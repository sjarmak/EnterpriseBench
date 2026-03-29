#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# Direct x/net dependency path for each repo
if grep -qiE 'x/net.*prometheus|prometheus.*x/net|prometheus.*go\.mod' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'x/net.*consul|consul.*x/net|consul.*go\.mod' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'x/net.*vault|vault.*x/net|vault.*go\.mod' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d dependency paths"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
