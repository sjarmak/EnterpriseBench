#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause file and mechanism
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kubernetes/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify cacher.go as root cause
if grep -qiE 'cacher\.go|cacher' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention PrevObject or previous object retaining wrong resourceVersion
if grep -qiE 'PrevObject|prev.*object|previous.*object|DeepCopyObject' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention resourceVersion being stale or wrong on DELETE
if grep -qiE 'resource.?[Vv]ersion.*stale|resource.?[Vv]ersion.*wrong|resource.?[Vv]ersion.*old|delete.*resource.?[Vv]ersion|resource.?[Vv]ersion.*delete' "$REPORT"; then
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
