#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# Path: x/net -> grpc-go (direct dep for http2 transport)
if grep -qiE 'x/net.*grpc|grpc.*x/net|http.?2.*transport' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Path: grpc-go -> etcd (etcd uses grpc-go)
if grep -qiE 'grpc.*etcd|etcd.*grpc' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Path: x/net -> kubernetes (direct or transitive via grpc-go)
if grep -qiE 'x/net.*kubernetes|kubernetes.*x/net|api.server' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d transitive paths"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
