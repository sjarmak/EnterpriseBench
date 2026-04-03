#!/usr/bin/env bash
# Checkpoint 3: Verify agent identified affected Flux resources
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/flux2/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must mention HelmRelease resources as affected
if grep -qiE 'HelmRelease|helm.*release.*resource' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention kustomize-controller as also affected
if grep -qiE 'kustomize.?controller|kustomiz' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d affected Flux resources"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
