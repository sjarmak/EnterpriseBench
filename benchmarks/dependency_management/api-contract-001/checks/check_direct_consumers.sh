#!/usr/bin/env bash
# Checkpoint 2: Verify agent found direct consumer files in etcd
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qiE 'auth/store|auth\.store' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'v3rpc/interceptor|interceptor\.go' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'v3rpc/grpc|grpc\.go' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'clientv3/auth|client.*auth' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d consumer files"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
