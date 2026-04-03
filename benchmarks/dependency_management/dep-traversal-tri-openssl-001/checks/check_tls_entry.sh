#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified git's HTTP/TLS configuration entry points
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/DEPENDENCY_TRACE.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DEPENDENCY_TRACE.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'http\.c|http\.sslCAInfo|sslCAInfo' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'http\.sslVerify|sslVerify|GIT_SSL' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'curl_easy_setopt|CURLOPT' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge "$TOTAL" ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d git TLS entry points"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
