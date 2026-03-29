#!/usr/bin/env bash
# Checkpoint 2: Verify agent found direct dependents of lodash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'webpack' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'jest' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE '@babel/traverse|babel.traverse' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d direct dependents"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
