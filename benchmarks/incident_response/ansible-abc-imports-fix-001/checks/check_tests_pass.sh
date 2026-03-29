#!/usr/bin/env bash
# check_tests_pass.sh — verify tests pass after migration
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

cd "$WORKSPACE/ansible"
if python3 -m pytest test/units/module_utils/common/ --timeout=60 -q >/dev/null 2>&1; then
    printf '{"score": 1.0, "passed": true, "detail": "Tests passed"}\n'
else
    printf '{"score": 0.0, "passed": false, "detail": "Tests failed after import migration"}\n'
fi
