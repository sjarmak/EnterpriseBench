#!/usr/bin/env bash
# Checkpoint 4: Verify agent identifies the bypass scenario and provides remediation
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must describe the dual-path inconsistency
if grep -qiE 'inconsisten|mismatch|gap|dual.*path|both.*tier|neither.*check' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must describe the bypass scenario (moving policy between tiers)
if grep -qiE 'mov.*polic.*tier|chang.*tier|escalat|bypass|unauthori' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must include severity assessment
if grep -qiE 'sever|critical|high|impact|risk' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must include remediation recommendations
if grep -qiE 'remedia|fix|recommend|mitigat|both.*tier|check.*both' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Bypass and remediation: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
