#!/usr/bin/env bash
# Checkpoint 2: Verify impact classification
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/babel/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

CONTENT=$(cat "$REPORT" | tr '[:upper:]' '[:lower:]')
if echo "$CONTENT" | grep -q 'minor'; then
  printf '{"score": 1.0, "passed": true, "reason": "Correct classification found"}\n'
else
  printf '{"score": 0.0, "passed": false, "reason": "Expected minor classification not found"}\n'
fi
