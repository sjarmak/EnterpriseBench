#!/usr/bin/env bash
# Checkpoint 4: Verify agent proposed correct remediation
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kubernetes/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must mention setting/updating the resourceVersion on the copied PrevObject
if grep -qiE 'set.*resource.?[Vv]ersion|update.*resource.?[Vv]ersion|copy.*resource.?[Vv]ersion|versioner|resource.?[Vv]ersion.*copy|resource.?[Vv]ersion.*set' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must reference the etcd watcher implementation as the correct pattern
if grep -qiE 'etcd.*watcher|etcd3.*watcher|existing.*logic|reference.*implementation|same.*pattern' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 1 ]; then
  PASSED=true
else
  PASSED=false
fi

printf '{"score": %s, "passed": %s, "reason": "Remediation quality: %d/%d key elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
