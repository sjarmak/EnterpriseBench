#!/usr/bin/env bash
# Checkpoint 3: Verify agent listed affected components
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention daemon monitor
if grep -qiE 'daemon.*monitor|monitor\.go' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention restart manager
if grep -qiE 'restart.*manager|RestartManager' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention libcontainerd or containerd client
if grep -qiE 'libcontainerd|containerd.*client|remote.*client' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention containerd shim runtime or task service components
if grep -qiE 'containerd.*shim|runtime/v2|shim.*lifecycle|task.*service|services/tasks' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d affected components"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
