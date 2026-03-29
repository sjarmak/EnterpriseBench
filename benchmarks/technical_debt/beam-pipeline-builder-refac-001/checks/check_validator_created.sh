#!/usr/bin/env bash
# check_validator_created.sh — verify PipelineOptionsValidator.java exists with Builder pattern
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
TARGET="$WORKSPACE/beam/sdks/java/core/src/main/java/org/apache/beam/sdk/options/PipelineOptionsValidator.java"

if [[ ! -f "$TARGET" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "PipelineOptionsValidator.java not found"}\n'
    exit 0
fi

FOUND=0
TOTAL=3

grep -q "class.*Builder" "$TARGET" 2>/dev/null && FOUND=$((FOUND + 1))
grep -q "validateRequired" "$TARGET" 2>/dev/null && FOUND=$((FOUND + 1))
grep -q "validate\b" "$TARGET" 2>/dev/null && FOUND=$((FOUND + 1))

SCORE=$(python3 -c "print(round($FOUND / $TOTAL, 2))")
PASSED=$([ "$FOUND" -ge 2 ] && echo true || echo false)
printf '{"score": %s, "passed": %s, "detail": "Found %d/%d required elements in validator"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
