#!/usr/bin/env bash
# Milestone verifier: Check that affected files are listed in the investigation.
WORKSPACE="${1:-.}"
REPORT="$WORKSPACE/etcd/INVESTIGATION.md"

if [ ! -f "$REPORT" ]; then
    echo '{"score": 0.0, "message": "INVESTIGATION.md not found"}'
    exit 1
fi

# Check that at least one .go file is mentioned
if grep -qE '\.go' "$REPORT"; then
    echo '{"score": 1.0, "message": "Go files identified in report"}'
    exit 0
else
    echo '{"score": 0.0, "message": "No Go files mentioned in investigation"}'
    exit 1
fi
