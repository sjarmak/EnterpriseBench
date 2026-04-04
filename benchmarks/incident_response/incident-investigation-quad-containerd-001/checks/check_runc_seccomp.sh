#!/usr/bin/env bash
# Checkpoint 3: Verify agent identified runc libcontainer seccomp BPF filter generation
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify runc seccomp filter generation file or function
if grep -qiE 'seccomp_linux\.go|libcontainer.*seccomp|runc.*seccomp.*filter|runc.*BPF' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention BPF filter or seccomp_rule or syscall filtering mechanism
if grep -qiE 'BPF.*filter|seccomp_rule|libseccomp|SCMP_ACT|seccomp.*syscall' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention unknown/unrecognized syscall handling (clone3, close_range, etc.)
if grep -qiE 'clone3|close_range|openat2|unrecognized.*syscall|unknown.*syscall|syscall.*not.*found' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d runc seccomp filter elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
