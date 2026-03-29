#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qi 'CVE-2021-44228' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'log4j.core|log4j-core' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE '2\.14\.1|2\.15\.0|2\.16\.0|Log4Shell' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d CVE details"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
