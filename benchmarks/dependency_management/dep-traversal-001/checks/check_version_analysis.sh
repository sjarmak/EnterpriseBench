#!/usr/bin/env bash
# Checkpoint 4: Verify agent analyzed version ranges for affected consumers
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2
# Agent should mention version range analysis
if grep -qiE 'affected|vulnerable|version.*range|< *4\.17' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Agent should classify at least one consumer as affected or not affected
if grep -qiE 'not.affected|unaffected|safe|patched|still.*vulnerable|needs.*upgrade' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Version analysis: %d/%d criteria met"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
