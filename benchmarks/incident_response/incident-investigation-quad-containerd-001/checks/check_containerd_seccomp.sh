#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced containerd CRI plugin seccomp handling
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify containerd CRI seccomp mapping file or function
if grep -qiE 'container_create_linux|cri.*server.*seccomp|containerd.*cri.*plugin' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention OCI spec mapping or runtime spec generation
if grep -qiE 'OCI.*spec|runtime.*spec|seccomp.*OCI|OCI.*seccomp|LinuxSeccomp' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention containerd seccomp profile processing
if grep -qiE 'containerd.*seccomp|seccomp_default|contrib.*seccomp|containerd.*profile' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d containerd CRI seccomp mapping elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
