#!/usr/bin/env bash
# check_remediations.sh — verify agent proposed remediation recommendations
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

REPORT="$WORKSPACE/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "security_audit.md not found"}\n'
    exit 0
fi

FOUND=0
TOTAL=2

grep -qiE "remediat|recommend|mitigat|fix|patch|harden" "$REPORT" && FOUND=$((FOUND + 1))
grep -qiE "risk.*assessment\|summary\|overall\|conclusion" "$REPORT" && FOUND=$((FOUND + 1))

SCORE=$(python3 -c "print(round($FOUND / $TOTAL, 2))")
PASSED=$([ "$FOUND" -ge 1 ] && echo true || echo false)
printf '{"score": %s, "passed": %s, "detail": "Remediation quality: %d/%d criteria"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
