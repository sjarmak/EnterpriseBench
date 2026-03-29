#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# urllib3 -> requests
if grep -qiE 'urllib3.*requests|requests.*urllib3|transport.*layer' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# requests -> botocore
if grep -qiE 'requests.*botocore|botocore.*requests' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# botocore -> boto3 (3-hop completion)
if grep -qiE 'botocore.*boto3|boto3.*botocore|3.hop|three.hop|transitive' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d transitive paths"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
