#!/usr/bin/env bash
# health_check.sh — Validates all repos cloned correctly.
# Usage: health_check.sh <repo1> <repo2> ...
# Reads marker files from /workspace/.markers/
set -euo pipefail

MARKER_DIR="/workspace/.markers"
FAILED=0

if [ $# -eq 0 ]; then
    # Auto-detect from marker directory
    for status_file in "$MARKER_DIR"/*.status; do
        [ -f "$status_file" ] || continue
        repo=$(basename "$status_file" .status)
        set -- "$@" "$repo"
    done
fi

for repo in "$@"; do
    status_file="$MARKER_DIR/${repo}.status"
    rev_file="$MARKER_DIR/${repo}.rev"

    if [ ! -f "$status_file" ]; then
        echo "FAIL: $repo — no status marker found"
        FAILED=1
        continue
    fi

    status=$(cat "$status_file")
    if [ "$status" != "OK" ]; then
        echo "FAIL: $repo — status is '$status', expected 'OK'"
        FAILED=1
        continue
    fi

    if [ ! -f "$rev_file" ]; then
        echo "WARN: $repo — no revision marker"
    else
        echo "OK: $repo — $(cat "$rev_file")"
    fi

    # Verify the repo directory actually has files
    if [ ! -d "/workspace/$repo/.git" ]; then
        echo "FAIL: $repo — directory exists but no .git"
        FAILED=1
        continue
    fi
done

if [ "$FAILED" -ne 0 ]; then
    echo ""
    echo "SANDBOX HEALTH CHECK FAILED — aborting"
    exit 1
fi

echo ""
echo "All repos healthy."
