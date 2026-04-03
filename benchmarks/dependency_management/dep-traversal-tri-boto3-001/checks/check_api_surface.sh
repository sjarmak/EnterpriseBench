#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified key classes and entry points in all three repos
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/DEPENDENCY_TRACE.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DEPENDENCY_TRACE.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'upload_file|S3Transfer|S3.resource' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'TransferManager|MultipartUploader|s3transfer' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'botocore.*client|create_multipart_upload|upload_part' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge "$TOTAL" ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d API surface areas across repos"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
