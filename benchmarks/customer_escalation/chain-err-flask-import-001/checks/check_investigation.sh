#!/usr/bin/env bash
# Milestone/checkpoint verifier: check that INVESTIGATION.md exists and has content.
# Receives workspace path as $1.
set -euo pipefail

WORKSPACE="${1:-.}"
REPORT="$WORKSPACE/flask/INVESTIGATION.md"

if [ ! -f "$REPORT" ]; then
    echo '{"score": 0.0, "message": "INVESTIGATION.md not found"}'
    exit 1
fi

# Check minimum length (at least 100 characters of content)
CHAR_COUNT=$(wc -c < "$REPORT")
if [ "$CHAR_COUNT" -lt 100 ]; then
    echo '{"score": 0.3, "message": "INVESTIGATION.md exists but is too short"}'
    exit 1
fi

# Check for key sections
HAS_CYCLE=0
HAS_MODULES=0
grep -qi "import.*cycle\|circular.*import\|import.*chain" "$REPORT" && HAS_CYCLE=1 || true
grep -qi "module\|file\|__init__" "$REPORT" && HAS_MODULES=1 || true

if [ "$HAS_CYCLE" -eq 1 ] && [ "$HAS_MODULES" -eq 1 ]; then
    echo '{"score": 1.0, "message": "Investigation report is complete"}'
    exit 0
elif [ "$HAS_CYCLE" -eq 1 ] || [ "$HAS_MODULES" -eq 1 ]; then
    echo '{"score": 0.6, "message": "Investigation report is partial"}'
    exit 1
else
    echo '{"score": 0.3, "message": "Investigation report lacks key content"}'
    exit 1
fi
