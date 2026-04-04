#!/usr/bin/env bash
# Checkpoint 4: Verify agent identified moby default seccomp profile and newer syscalls
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must identify moby seccomp profile files
if grep -qiE 'profiles/seccomp|seccomp\.go|default_linux\.go|moby.*seccomp.*profile' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention default profile including newer syscalls
if grep -qiE 'default.*profile|DefaultProfile|RuntimeDefault|moby.*default' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the difference between default and custom profiles
if grep -qiE 'custom.*profile.*missing|profile.*outdated|profile.*update|newer.*syscall|custom.*default.*differ|whitelist.*missing' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d moby default seccomp profile elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
