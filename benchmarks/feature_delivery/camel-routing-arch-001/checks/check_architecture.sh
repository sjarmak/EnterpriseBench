#!/usr/bin/env bash
# check_architecture.sh — verify agent produced coherent architectural analysis
set -euo pipefail

ANSWER="${WORKSPACE:-/workspace}/agent_output/answer.json"
if [[ ! -f "$ANSWER" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "No agent output found"}\n'
    exit 0
fi

TEXT=$(tr '[:upper:]' '[:lower:]' < "$ANSWER")

FOUND=0
TOTAL=3

echo "$TEXT" | grep -q "component.*endpoint\|endpoint.*consumer\|consumer.*processor\|processor.*producer" && FOUND=$((FOUND + 1))
echo "$TEXT" | grep -q "pattern\|design pattern\|eip\|enterprise integration" && FOUND=$((FOUND + 1))
# Must have reasonable length (at least 500 chars of analysis)
LEN=$(echo "$TEXT" | wc -c)
[ "$LEN" -ge 500 ] && FOUND=$((FOUND + 1))

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
PASSED=$([ "$FOUND" -ge 2 ] && echo true || echo false)
printf '{"score": %s, "passed": %s, "detail": "Architecture analysis quality: %d/%d criteria met"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
