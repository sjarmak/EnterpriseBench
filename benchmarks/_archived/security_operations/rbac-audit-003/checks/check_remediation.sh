#!/usr/bin/env bash
# Checkpoint 4: Verify agent provides specific remediation steps
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must include remediation section
if grep -qiE 'remedia|fix|recommend|solution' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must reference specific files to change
if grep -qiE 'context\.go|robot\.go' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must describe what to add/change
if grep -qiE 'add.*filter|pass.*filter|includ.*filter|wildcard.*valid' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Remediation: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
