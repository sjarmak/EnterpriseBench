#!/usr/bin/env bash
# Checkpoint 3: Verify agent identified affected components in all three repos
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must mention moby/Docker daemon component
if grep -qiE 'moby|docker.*daemon|daemon/start' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention containerd component
if grep -qiE 'containerd' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention runc component
if grep -qiE 'runc|libcontainer' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d affected runtime components"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
