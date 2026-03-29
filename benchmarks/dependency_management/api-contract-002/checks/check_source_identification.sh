#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified removed type aliases
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'balancer/balancer\.go|balancer\.go' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'resolver/resolver\.go|resolver\.go' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'alias|type.*alias|backward.*compat|removed.*type' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d source elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
