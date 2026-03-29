#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2
if grep -qiE 'go\.sum|go\.mod|resolved|pinned|version' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'affected|vulnerable|patched|needs.*upgrade|< *0\.7' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Version analysis: %d/%d criteria met"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
