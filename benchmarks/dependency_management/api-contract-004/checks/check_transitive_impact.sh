#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'test.*mock|mock.*test|fake.*balancer' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'MetricsRecorder|BuildOptions|metrics' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'gracefulswitch|graceful.*switch|outlier' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 1 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d transitive impact areas"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
