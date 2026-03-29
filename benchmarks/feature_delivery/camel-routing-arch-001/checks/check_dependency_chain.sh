#!/usr/bin/env bash
# check_dependency_chain.sh — verify agent traced the reification chain
set -euo pipefail

# Look for agent output
ANSWER=""
for f in "${WORKSPACE:-/workspace}/answer.json" "${WORKSPACE:-/workspace}/logs/agent/solution.md"; do
    if [[ -f "$f" ]]; then
        ANSWER="$f"
        break
    fi
done

if [[ -z "$ANSWER" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "No agent output found"}\n'
    exit 0
fi

TEXT=$(cat "$ANSWER" | tr '[:upper:]' '[:lower:]')

FOUND=0
TOTAL=4

echo "$TEXT" | grep -q "routereifier\|route.*reifier" && FOUND=$((FOUND + 1))
echo "$TEXT" | grep -q "routedefinition\|route.*definition" && FOUND=$((FOUND + 1))
echo "$TEXT" | grep -q "pipeline" && FOUND=$((FOUND + 1))
echo "$TEXT" | grep -q "channel" && FOUND=$((FOUND + 1))

SCORE=$(python3 -c "print(round($FOUND / $TOTAL, 2))")
PASSED=$([ "$FOUND" -ge 2 ] && echo true || echo false)
printf '{"score": %s, "passed": %s, "detail": "Found %d/%d reification chain concepts"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
