#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified affected packages
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/rust/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qiE 'rustc_ast_passes' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'rustc_builtin_macros' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'rustc_codegen_llvm' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'rustc_codegen_gcc' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Compute score as proper decimal
if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d affected packages"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
