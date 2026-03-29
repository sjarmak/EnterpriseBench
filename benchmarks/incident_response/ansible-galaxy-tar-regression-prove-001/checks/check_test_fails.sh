#!/usr/bin/env bash
# check_test_fails.sh — verify regression test fails on buggy code
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

TEST_FILE="$WORKSPACE/regression_test.py"
if [[ ! -f "$TEST_FILE" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "regression_test.py not found"}\n'
    exit 0
fi

# Run the test — it should FAIL on the buggy code
cd "$WORKSPACE"
if python3 -m pytest --timeout=60 "$TEST_FILE" -q 2>&1; then
    # Test passed = bad (it should fail on buggy code)
    printf '{"score": 0.0, "passed": false, "detail": "Test passed on buggy code — it should fail"}\n'
else
    printf '{"score": 1.0, "passed": true, "detail": "Test correctly fails on buggy code"}\n'
fi
