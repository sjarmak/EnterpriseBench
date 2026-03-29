#!/usr/bin/env bash
# Checkpoint 2: Verify agent found affected etcd files
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'picker/err|err\.go' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'roundrobin.*balanced|roundrobin_balanced' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'resolver/endpoint|endpoint\.go' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d consumer files"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
