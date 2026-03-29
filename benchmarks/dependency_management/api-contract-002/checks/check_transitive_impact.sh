#!/usr/bin/env bash
# Checkpoint 3: Verify agent traced custom balancer dependency chain
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# Must identify etcd's custom balancer as a key component
if grep -qiE 'custom.*balancer|balancer.*custom|clientv3.*balancer' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must trace picker implementations
if grep -qiE 'Picker|picker.*implement|implement.*picker' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must trace resolver implementation
if grep -qiE 'endpoint.*resolver|resolver.*endpoint|custom.*resolver' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d dependency chain components"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
