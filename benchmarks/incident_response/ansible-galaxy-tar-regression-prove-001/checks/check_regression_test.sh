#!/usr/bin/env bash
# check_regression_test.sh — verify regression_test.py exists and is valid
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

TEST_FILE="$WORKSPACE/regression_test.py"
if [[ ! -f "$TEST_FILE" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "regression_test.py not found"}\n'
    exit 0
fi

# Check it has test functions
TEST_COUNT=$(grep -c "def test_" "$TEST_FILE" 2>/dev/null || echo 0)
if [ "$TEST_COUNT" -ge 1 ]; then
    SCORE=$(python3 -c "print(round(min(1.0, $TEST_COUNT / 2), 2))")
    printf '{"score": %s, "passed": true, "detail": "regression_test.py has %d test functions"}\n' "$SCORE" "$TEST_COUNT"
else
    printf '{"score": 0.2, "passed": false, "detail": "regression_test.py exists but has no test_ functions"}\n'
fi
