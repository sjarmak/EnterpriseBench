#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified kubelet CRI seccomp profile conversion
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify kubelet seccomp conversion file or function
if grep -qiE 'kuberuntime_container_linux|kuberuntime.*seccomp|security_context\.go' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention CRI SecurityContext or LinuxContainerSecurityContext
if grep -qiE 'LinuxContainerSecurityContext|CRI.*seccomp|SecurityContext.*seccomp|seccomp.*CRI' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention kubelet or pkg/kubelet role in seccomp conversion
if grep -qiE 'kubelet.*seccomp|kubelet.*convert|kubelet.*profile|pkg/kubelet' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d kubelet seccomp conversion elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
