#!/usr/bin/env bash
# check_architecture.sh — verify agent produced coherent architectural analysis
set -euo pipefail

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
TOTAL=3

echo "$TEXT" | grep -q "component.*endpoint\|endpoint.*consumer\|consumer.*processor\|processor.*producer" && FOUND=$((FOUND + 1))
echo "$TEXT" | grep -q "pattern\|design pattern\|eip\|enterprise integration" && FOUND=$((FOUND + 1))
# Must have reasonable length (at least 500 chars of analysis)
LEN=$(echo "$TEXT" | wc -c)
[ "$LEN" -ge 500 ] && FOUND=$((FOUND + 1))

SCORE=$(python3 -c "print(round($FOUND / $TOTAL, 2))")
PASSED=$([ "$FOUND" -ge 2 ] && echo true || echo false)
printf '{"score": %s, "passed": %s, "detail": "Architecture analysis quality: %d/%d criteria met"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
