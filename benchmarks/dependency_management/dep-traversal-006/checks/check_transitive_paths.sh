#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# protobuf -> grpc-go path
if grep -qiE 'protobuf.*grpc|grpc.*protobuf' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# grpc-go or control-plane -> istio path
if grep -qiE 'grpc.*istio|control.plane.*istio|istio.*grpc|istio.*control' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Any type / JSON unmarshal code path analysis
if grep -qiE 'Any|protojson|jsonpb|unmarshal|json.*unmarshal' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d transitive paths"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
