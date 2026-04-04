#!/usr/bin/env bash
# Checkpoint 5: Verify agent traced cross-repo seccomp error propagation chain
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention kubelet role in the chain
if grep -qiE 'kubelet.*CRI|kubelet.*seccomp|kubelet.*error|kubelet.*containerd' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention containerd as intermediary in the chain
if grep -qiE 'containerd.*runc|containerd.*OCI|containerd.*shim|CRI.*containerd' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention runc as the point of failure
if grep -qiE 'runc.*fail|runc.*error|runc.*seccomp|BPF.*fail|filter.*fail' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention moby default profile as reference or comparison point
if grep -qiE 'moby.*default|default.*profile.*include|moby.*seccomp|docker.*seccomp' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d cross-repo error chain components"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
