#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# requests -> botocore path
if grep -qiE 'requests.*botocore|botocore.*requests' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# botocore -> boto3 path
if grep -qiE 'botocore.*boto3|boto3.*botocore' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# boto3/botocore -> awscli path
if grep -qiE 'boto.*awscli|awscli.*boto|aws.*cli.*boto' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d transitive paths"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
