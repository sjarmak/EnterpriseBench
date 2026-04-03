#!/usr/bin/env bash
# Checkpoint 1: Verify agent locates the FGAP V2 implementation
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must reference FGAP directory or files
if grep -qiE 'fgap|fine.grained.*admin.*permission' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must reference RealmPermissionsV2
if grep -qiE 'RealmPermissionsV2' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "FGAP location: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
