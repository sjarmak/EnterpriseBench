#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause file and function
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kubernetes/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify watch_cache.go as the root cause file
if grep -qiE 'watch_cache\.go|watch_cache' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the empty cache or off-by-one issue
if grep -qiE 'empty.*cache|off.by.one|resource.?version.*mismatch|oldest.*resource' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the function or the specific mechanism
if grep -qiE 'GetAllEventsSince|getAllEventsSince|resourceVersion.*empty|cache.*empty.*event' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 2 ]; then
  PASSED=true
else
  PASSED=false
fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d root cause elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
