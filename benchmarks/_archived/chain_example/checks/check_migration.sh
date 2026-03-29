#!/usr/bin/env bash
# Checkpoint verifier: Check that code migration changes were applied.
WORKSPACE="${1:-.}"

score=0.0
msg=""

# Check for migration summary
if [ -f "$WORKSPACE/etcd/MIGRATION_SUMMARY.md" ]; then
    score=$(echo "$score + 0.5" | bc)
    msg="migration_summary_found"
else
    msg="no_migration_summary"
fi

# Check for any modified/new Go files (evidence of code changes)
go_files=$(find "$WORKSPACE/etcd" -name "*.go" -newer "$WORKSPACE/etcd/INVESTIGATION.md" 2>/dev/null | wc -l)
if [ "$go_files" -gt 0 ]; then
    score=$(echo "$score + 0.5" | bc)
    msg="$msg, ${go_files}_go_files_modified"
else
    msg="$msg, no_go_files_modified"
fi

echo "{\"score\": $score, \"message\": \"$msg\"}"
if (( $(echo "$score >= 0.5" | bc -l) )); then
    exit 0
else
    exit 1
fi
