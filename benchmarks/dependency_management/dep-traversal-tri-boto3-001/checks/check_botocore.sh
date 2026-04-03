#!/usr/bin/env bash
# Checkpoint 3: Verify agent identified botocore's low-level API operations and retry logic
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/DEPENDENCY_TRACE.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DEPENDENCY_TRACE.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qiE 'CreateMultipartUpload|create_multipart' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'UploadPart|upload_part' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'CompleteMultipartUpload|complete_multipart' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'retry|serialize|client\.py' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d botocore integration concepts"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
