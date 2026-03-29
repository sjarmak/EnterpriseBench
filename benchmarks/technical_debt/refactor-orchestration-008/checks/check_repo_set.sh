#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified all repos/components requiring changes
set -euo pipefail

ANSWER="${WORKSPACE:-/workspace}/REFACTOR_PLAN.md"
if [[ ! -f "$ANSWER" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "REFACTOR_PLAN.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qiE 'go-grpc-middleware|grpc.middleware' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'etcd' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'kubernetes' "$ANSWER"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'grpc-prometheus|go-grpc-prometheus' "$ANSWER"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d repos/components in plan"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
