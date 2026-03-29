#!/usr/bin/env bash
# Milestone verifier: Check that investigation report exists and has required sections.
# Usage: check_investigation.sh /path/to/workspace

WORKSPACE="${1:-.}"

REPORT="$WORKSPACE/etcd/INVESTIGATION.md"

if [ ! -f "$REPORT" ]; then
    echo '{"score": 0.0, "message": "INVESTIGATION.md not found"}'
    exit 1
fi

# Check for required sections
score=0.0
missing=""

if grep -qi "affected files" "$REPORT"; then
    score=$(echo "$score + 0.4" | bc)
else
    missing="$missing affected_files"
fi

if grep -qi "migration order" "$REPORT"; then
    score=$(echo "$score + 0.3" | bc)
else
    missing="$missing migration_order"
fi

if grep -qi "risk" "$REPORT"; then
    score=$(echo "$score + 0.3" | bc)
else
    missing="$missing risk_assessment"
fi

if [ -z "$missing" ]; then
    echo "{\"score\": $score, \"message\": \"All required sections present\"}"
    exit 0
else
    echo "{\"score\": $score, \"message\": \"Missing sections:$missing\"}"
    exit 1
fi
