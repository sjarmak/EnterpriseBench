#!/usr/bin/env bash
# check_findings.sh — verify agent identified at least 3 security findings
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

REPORT="$WORKSPACE/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "security_audit.md not found"}\n'
    exit 0
fi

# Count finding sections (look for numbered findings, severity markers, or finding headers)
FINDINGS=$(grep -ciE "finding|vulnerability|severity|critical|high|medium|low|timing.*attack|replay|fallback" "$REPORT" || echo 0)

# Require at least 3 distinct findings
if [ "$FINDINGS" -ge 6 ]; then
    SCORE="1.0"
    PASSED="true"
elif [ "$FINDINGS" -ge 3 ]; then
    SCORE="0.7"
    PASSED="true"
elif [ "$FINDINGS" -ge 1 ]; then
    SCORE="0.3"
    PASSED="false"
else
    SCORE="0.0"
    PASSED="false"
fi

printf '{"score": %s, "passed": %s, "detail": "Found %d finding-related references"}\n' "$SCORE" "$PASSED" "$FINDINGS"
