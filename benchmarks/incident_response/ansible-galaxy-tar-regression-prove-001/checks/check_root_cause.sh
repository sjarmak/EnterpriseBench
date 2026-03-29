#!/usr/bin/env bash
# check_root_cause.sh — verify agent identified the tar extraction fragility
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
GT_FILE="$TASK_DIR/ground_truth.json"

# Check if agent referenced the key files
FOUND=0
TOTAL=2

# Look for any agent output referencing the key files
ALL_TEXT=""
while IFS= read -r f; do
    ALL_TEXT="$ALL_TEXT $(cat "$f" 2>/dev/null)"
done < <(find "$WORKSPACE" -maxdepth 1 \( -name "*.py" -o -name "*.md" -o -name "*.json" \) 2>/dev/null | head -5)
# Also check agent_output/ directory
if [[ -d "$WORKSPACE/agent_output" ]]; then
    ALL_TEXT="$ALL_TEXT $(cat "$WORKSPACE/agent_output"/* 2>/dev/null)"
fi

if echo "$ALL_TEXT" | grep -qi "concrete_artifact_manager\|tar.*member\|getmember\|_tar_member"; then
    FOUND=$((FOUND + 1))
fi
if echo "$ALL_TEXT" | grep -qi "collection.*init\|galaxy.*collection\|tarfile"; then
    FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {t=($TOTAL>1?$TOTAL:1); printf \"%.2f\", $FOUND/t}")
PASSED=$([ "$FOUND" -ge 1 ] && echo true || echo false)
printf '{"score": %s, "passed": %s, "detail": "Found %d/%d root cause indicators"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
