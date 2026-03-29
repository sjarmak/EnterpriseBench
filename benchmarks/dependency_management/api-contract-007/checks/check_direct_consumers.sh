#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'istio' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'grpc-go|grpc.*go' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'google-cloud|cloud\.google|googleapis' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d affected consumers"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
