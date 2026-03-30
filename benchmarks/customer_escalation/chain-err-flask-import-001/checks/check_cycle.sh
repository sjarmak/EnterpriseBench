#!/usr/bin/env bash
# Milestone/checkpoint verifier: check that the import cycle is correctly identified.
# Receives workspace path as $1.
set -euo pipefail

WORKSPACE="${1:-.}"
REPORT="$WORKSPACE/flask/INVESTIGATION.md"

if [ ! -f "$REPORT" ]; then
    echo '{"score": 0.0, "message": "INVESTIGATION.md not found"}'
    exit 1
fi

SCORE=0.0
MSG=""

# Check for mentions of key modules in the cycle
HAS_JSON=0
HAS_GLOBALS=0
HAS_APP=0
HAS_INIT=0

grep -qi "json" "$REPORT" && HAS_JSON=1 || true
grep -qi "globals" "$REPORT" && HAS_GLOBALS=1 || true
grep -qi "app\.py\|flask/app\|flask\.app" "$REPORT" && HAS_APP=1 || true
grep -qi "__init__\|flask/__init__" "$REPORT" && HAS_INIT=1 || true

TOTAL=$((HAS_JSON + HAS_GLOBALS + HAS_APP + HAS_INIT))

if [ "$TOTAL" -ge 3 ]; then
    SCORE=1.0
    MSG="Import cycle correctly identifies key modules"
elif [ "$TOTAL" -ge 2 ]; then
    SCORE=0.6
    MSG="Import cycle partially identified ($TOTAL/4 key modules found)"
else
    SCORE=0.2
    MSG="Import cycle poorly identified ($TOTAL/4 key modules found)"
fi

echo "{\"score\": $SCORE, \"message\": \"$MSG\"}"
if [ "$TOTAL" -ge 3 ]; then
    exit 0
else
    exit 1
fi
