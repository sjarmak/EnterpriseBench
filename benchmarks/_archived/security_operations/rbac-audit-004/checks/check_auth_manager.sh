#!/usr/bin/env bash
# Checkpoint 1: Verify agent locates AppAuthManager.java
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must reference AppAuthManager
if grep -qiE 'AppAuthManager' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must reference the token extraction method or Authorization header parsing
if grep -qiE 'extract.*token|token.*extract|Authorization.*header|Bearer.*pars' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Auth manager location: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
