#!/usr/bin/env bash
# check_root_cause.sh — verify agent identified the tar extraction fragility
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
GT_FILE="$TASK_DIR/ground_truth.json"

# Check if agent referenced the key files
FOUND=0
TOTAL=2

# Look for any agent output referencing the key files
AGENT_OUTPUT=$(find "$WORKSPACE" -maxdepth 1 -name "*.py" -o -name "*.md" -o -name "*.json" 2>/dev/null | head -5)
ALL_TEXT=""
for f in $AGENT_OUTPUT; do
    ALL_TEXT="$ALL_TEXT $(cat "$f" 2>/dev/null)"
done

if echo "$ALL_TEXT" | grep -qi "concrete_artifact_manager\|tar.*member\|getmember\|_tar_member"; then
    FOUND=$((FOUND + 1))
fi
if echo "$ALL_TEXT" | grep -qi "collection.*init\|galaxy.*collection\|tarfile"; then
    FOUND=$((FOUND + 1))
fi

SCORE=$(python3 -c "print(round($FOUND / max($TOTAL, 1), 2))")
PASSED=$([ "$FOUND" -ge 1 ] && echo true || echo false)
printf '{"score": %s, "passed": %s, "detail": "Found %d/%d root cause indicators"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
