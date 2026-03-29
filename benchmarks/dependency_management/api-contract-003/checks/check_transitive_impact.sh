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
if grep -qiE 'grpc.*etcd.*kubernetes|chain.*three|3.*repo' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must identify vendoring as propagation mechanism
if grep -qiE 'vendor|vendoring|go.*mod' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Must identify multiple k8s subsystems affected
if grep -qiE 'kubelet|apiserver|kube.proxy|staging' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d chain elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
