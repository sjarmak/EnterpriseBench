#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the error across all three repos
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention Docker daemon initiating container start
if grep -qiE 'daemon.*start|docker.*daemon|moby.*start' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention containerd shim as intermediary
if grep -qiE 'containerd.*shim|shim.*process|containerd.*delegat' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention runc process execution
if grep -qiE 'runc.*exec|runc.*process|runc.*create' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must trace error propagation back up the chain
if grep -qiE 'OCI.*runtime|error.*propagat|error.*return|user.*visible.*error' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d error chain steps across repos"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
