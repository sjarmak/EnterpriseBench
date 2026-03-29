#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the error chain
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kubernetes/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention client-go or informer
if grep -qiE 'client.go|informer' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention cacher or watch cache filtering
if grep -qiE 'cacher|watch.*cache.*filter|processEvent' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention etcd3 watcher as the correct reference
if grep -qiE 'etcd3.*watcher|etcd.*watcher\.go|etcd.*correct' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the filter conversion (Modified -> Deleted)
if grep -qiE 'filter|namespace.*match|curObjPasses|oldObjPasses|convert.*delete|modified.*delete' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 3 ]; then
  PASSED=true
else
  PASSED=false
fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d error chain components"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
