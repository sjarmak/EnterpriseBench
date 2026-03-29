#!/usr/bin/env bash
# check_validation_result.sh — verify ValidationResult class exists
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

# Look for ValidationResult in the options directory
RESULT_FILE=$(find "$WORKSPACE/beam/sdks/java/core/src/main/java/org/apache/beam/sdk/options/" \
    -name "ValidationResult.java" 2>/dev/null | head -1)

if [[ -z "$RESULT_FILE" ]]; then
    # Check if it's nested inside the validator
    if grep -q "class ValidationResult" "$WORKSPACE/beam/sdks/java/core/src/main/java/org/apache/beam/sdk/options/PipelineOptionsValidator.java" 2>/dev/null; then
        printf '{"score": 1.0, "passed": true, "detail": "ValidationResult found as inner class"}\n'
    else
        printf '{"score": 0.0, "passed": false, "detail": "ValidationResult class not found"}\n'
    fi
else
    printf '{"score": 1.0, "passed": true, "detail": "ValidationResult.java found"}\n'
fi
