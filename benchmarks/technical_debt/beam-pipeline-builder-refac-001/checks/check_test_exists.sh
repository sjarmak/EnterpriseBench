#!/usr/bin/env bash
# check_test_exists.sh — verify test file for the validator exists
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

TEST_FILE=$(find "$WORKSPACE/beam/sdks/java/core/src/" -name "*PipelineOptionsValidator*Test*" -o -name "*ValidatorTest*" 2>/dev/null | head -1)

if [[ -z "$TEST_FILE" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "No test file found for PipelineOptionsValidator"}\n'
else
    TEST_COUNT=$(grep -c "@Test\|void test" "$TEST_FILE" 2>/dev/null || echo 0)
    SCORE=$(awk "BEGIN {s=$TEST_COUNT/2; if(s>1)s=1; printf \"%.2f\", s}")
    PASSED=$([ "$TEST_COUNT" -ge 1 ] && echo true || echo false)
    printf '{"score": %s, "passed": %s, "detail": "Test file found with %d tests"}\n' "$SCORE" "$PASSED" "$TEST_COUNT"
fi
