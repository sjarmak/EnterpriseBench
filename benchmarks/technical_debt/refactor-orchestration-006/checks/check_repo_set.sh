#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified key staging repos and components
set -euo pipefail

ANSWER="${WORKSPACE:-/workspace}/REFACTOR_PLAN.md"
if [[ ! -f "$ANSWER" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "REFACTOR_PLAN.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=5
if grep -qiE 'apimachinery' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'client-go' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'apiserver' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'distroless|base.image' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'k8s\.io/api[^a-z]' "$ANSWER"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 4 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d key components in plan"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
