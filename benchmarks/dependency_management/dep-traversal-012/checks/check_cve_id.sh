#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qi 'CVE-2022-0778' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE '1\.0\.2|1\.1\.1|3\.0\.[01]' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'BN_mod_sqrt|openssl|infinite.loop' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d CVE details"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
