#!/usr/bin/env bash
# Checkpoint 1: Verify agent describes the system vs project robot RBAC model
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must distinguish system vs project robots
if grep -qiE 'system.*robot|robot.*system' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'project.*robot|robot.*project' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must reference RBAC evaluator
if grep -qiE 'rbac.*evaluat|evaluat.*rbac|permission.*evaluat' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "RBAC architecture: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
