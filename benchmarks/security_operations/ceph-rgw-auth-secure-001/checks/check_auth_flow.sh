#!/usr/bin/env bash
# check_auth_flow.sh — verify agent documented the S3 auth flow
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

REPORT="$WORKSPACE/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "security_audit.md not found"}\n'
    exit 0
fi

FOUND=0
TOTAL=3

grep -qi "rgw_auth_s3" "$REPORT" && FOUND=$((FOUND + 1))
grep -qi "signature.*v[24]\|aws.*sign\|SigV4\|SignatureV4" "$REPORT" && FOUND=$((FOUND + 1))
grep -qi "rgw_rest_s3\|rgw_auth\.h" "$REPORT" && FOUND=$((FOUND + 1))

SCORE=$(python3 -c "print(round($FOUND / $TOTAL, 2))")
PASSED=$([ "$FOUND" -ge 2 ] && echo true || echo false)
printf '{"score": %s, "passed": %s, "detail": "Auth flow documentation: %d/%d elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
