#!/usr/bin/env bash
# Checkpoint 4: Verify agent provides severity and remediation
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must include severity assessment
if grep -qiE 'sever|CVSS|critical|high.*risk|impact' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must include CVE reference
if grep -qiE 'CVE-2026-3121|CVE.*3121' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must include remediation
if grep -qiE 'remedia|fix|recommend|mitigat|patch' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Severity and remediation: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
