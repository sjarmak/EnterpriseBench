#!/usr/bin/env bash
# Checkpoint 4: Verify agent provides remediation recommendations
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must include remediation section
if grep -qiE 'remedia|fix|recommend|mitigat' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must mention specific validation changes
if grep -qiE 'validat.*Bearer|case.insensitiv.*check|regex.*b64|strict.*pars' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must reference the CVE
if grep -qiE 'CVE-2026-0707|GHSA-gv94' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Remediation: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
