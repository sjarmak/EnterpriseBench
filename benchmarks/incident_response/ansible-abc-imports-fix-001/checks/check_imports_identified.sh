#!/usr/bin/env bash
# check_imports_identified.sh — verify agent found files importing _collections_compat
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

# Check if agent left any evidence of identifying the imports
# Look for modified files or an answer file
FOUND=0
TOTAL=2

# Check if agent found the compat module
if find "$WORKSPACE/ansible" -name "*.py" -newer "$WORKSPACE/.task_start" 2>/dev/null | head -1 | grep -q .; then
    FOUND=$((FOUND + 1))
fi

# Check if _collections_compat.py was identified in agent's output (answer.json, patches, or logs)
if grep -rq "_collections_compat" "$WORKSPACE/agent_output/" 2>/dev/null; then
    FOUND=$((FOUND + 1))
fi

SCORE=$(python3 -c "print(round($FOUND / max($TOTAL, 1), 2))")
PASSED=$([ "$FOUND" -ge 1 ] && echo true || echo false)
printf '{"score": %s, "passed": %s, "detail": "Identified %d/%d import sources"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
