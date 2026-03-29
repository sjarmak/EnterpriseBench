#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified all packages requiring changes
set -euo pipefail

ANSWER="${WORKSPACE:-/workspace}/REFACTOR_PLAN.md"
if [[ ! -f "$ANSWER" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "REFACTOR_PLAN.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=5
if grep -qiE 'preset-env' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'preset-react' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'plugin-transform-react' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'plugin-transform-property-mutators' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE '@babel/core' "$ANSWER"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 4 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d key packages in plan"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
