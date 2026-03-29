#!/usr/bin/env bash
# Checkpoint 2: Verify agent identifies the RBAC evaluator chain gap
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must reference context.go
if grep -qiE 'context\.go|security/robot' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must mention filterRobotPolicies or policy filtering
if grep -qiE 'filterRobotPolic|robot.*polic.*filter|filter.*robot.*polic' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must identify the gap (missing parameter, inconsistency)
if grep -qiE 'missing|inconsisten|gap|not.*pass|not.*includ|absent' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Evaluator chain: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
