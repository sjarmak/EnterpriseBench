#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
# Must find etcd consumers
if grep -qiE 'etcd.*transport|etcd.*import.*grpc' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must find k8s vendor directory
if grep -qiE 'vendor.*grpc.*transport|kubernetes.*vendor' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must find apiserver as affected
if grep -qiE 'apiserver|api.server|api-server' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must find clientconn.go or server.go as key files
if grep -qiE 'clientconn|server\.go|stream\.go' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d consumer areas"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
