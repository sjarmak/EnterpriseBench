#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the error chain across components
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/kubernetes/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention API server or watch handler
if grep -qiE 'api.?server|watch.*handler|kube-apiserver' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention cacher.go or the cacher component
if grep -qiE 'cacher\.go|cacher|watch.*cache.*layer' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention watch_cache.go or watch cache storage
if grep -qiE 'watch_cache\.go|watch_cache|watchCache' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention etcd or the storage backend
if grep -qiE 'etcd|storage.*backend|etcd3.*watcher' "$REPORT"; then
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
