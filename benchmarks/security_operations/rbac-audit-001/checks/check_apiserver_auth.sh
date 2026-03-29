#!/usr/bin/env bash
# Checkpoint 2: Verify agent describes the apiserver Update() authorization path
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must reference apiserver storage files
if grep -qiE 'storage\.go|apiserver.*registry' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must mention Update method or update operation
if grep -qiE 'Update\(\)|update.*method|update.*operation' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must identify that apiserver checks old tier only (not new)
if grep -qiE 'old.*tier|existing.*tier|original.*tier|source.*tier|current.*tier' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Apiserver auth analysis: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
