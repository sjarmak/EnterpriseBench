#!/usr/bin/env bash
# Checkpoint 2: Verify agent identifies RFC 6750 compliance violations
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Case sensitivity issue
if grep -qiE 'case.insensitiv|case.sensitiv|[Bb]earer.*case' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Whitespace handling
if grep -qiE 'whitespace|separator|space.*char|ASCII.*space' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Token character validation
if grep -qiE 'b64token|token.*validat|character.*set|charset|token.*format' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# RFC 6750 reference
if grep -qiE 'RFC.?6750|rfc.?6750' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "RFC violations: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
