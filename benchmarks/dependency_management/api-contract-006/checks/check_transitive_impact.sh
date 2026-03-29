#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# Must identify three-repo chain
if grep -qiE 'envoy.*go-control.*istio|chain|propagat' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must identify proto type migration (Cluster, Endpoint, Listener, Route)
if grep -qiE 'Cluster.*Endpoint|CDS.*EDS|LDS.*RDS' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must quantify scale (150+ files across istio)
if grep -qiE '150|hundred|large.*scale|48.*file|107.*file' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d chain elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
