#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the shutdown error chain
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention signal handling (SIGINT/SIGTERM)
if grep -qiE 'SIGINT|SIGTERM|signal.*interrupt|signal.*handler' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention ExitOnNext or restart manager being stopped
if grep -qiE 'ExitOnNext|exit.*on.*next|restart.*manager.*stop' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention containerd shim or TaskDelete event
if grep -qiE 'containerd.*shim|TaskDelete|task.*delete|shim.*disconnect' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the monitor or handleContainerExit
if grep -qiE 'monitor|handleContainerExit|handle.*exit' "$REPORT"; then
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
