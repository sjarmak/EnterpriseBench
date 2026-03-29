#!/usr/bin/env bash
# test_runner.sh — Cross-repo test runner for EnterpriseBench tasks.
# This is a skeleton. Each task may override or extend with task-specific logic.
#
# Usage: /workspace/test.sh [checkpoint_name]
set -euo pipefail

WORKSPACE="/workspace"

echo "=== EnterpriseBench Cross-Repo Test Runner ==="
echo "Workspace: $WORKSPACE"
echo "Repos:"
for dir in "$WORKSPACE"/*/; do
    [ -d "$dir/.git" ] && echo "  - $(basename "$dir")"
done
echo ""

# If a checkpoint name is given, run only that checkpoint's verifier
if [ -n "${1:-}" ]; then
    CHECKPOINT="$1"
    if [[ "$CHECKPOINT" =~ [^a-zA-Z0-9_-] ]]; then
        echo '{"score": 0.0, "passed": false, "detail": "Invalid checkpoint name"}'
        exit 1
    fi
    VERIFIER="$WORKSPACE/.verifiers/${CHECKPOINT}.sh"
    if [ -f "$VERIFIER" ]; then
        echo "Running checkpoint: $CHECKPOINT"
        bash "$VERIFIER"
        exit $?
    else
        echo "ERROR: No verifier found for checkpoint '$CHECKPOINT'"
        echo "Looked at: $VERIFIER"
        exit 1
    fi
fi

# Default: run all verifiers in order
if [ -d "$WORKSPACE/.verifiers" ]; then
    TOTAL=0
    PASSED=0
    for verifier in "$WORKSPACE"/.verifiers/*.sh; do
        [ -f "$verifier" ] || continue
        name=$(basename "$verifier" .sh)
        TOTAL=$((TOTAL + 1))
        echo "--- Checkpoint: $name ---"
        if bash "$verifier"; then
            echo "  PASS"
            PASSED=$((PASSED + 1))
        else
            echo "  FAIL"
        fi
        echo ""
    done
    echo "Results: $PASSED/$TOTAL checkpoints passed"
else
    echo "No .verifiers/ directory found. Nothing to run."
    echo "This runner expects checkpoint verifiers in /workspace/.verifiers/"
fi
