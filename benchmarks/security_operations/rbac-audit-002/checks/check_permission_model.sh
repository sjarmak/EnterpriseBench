#!/usr/bin/env bash
# Checkpoint 2: Verify agent describes the permission model and manage-clients scope
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must describe the permission model
if grep -qiE 'permission.*model|permission.*system|admin.*permission' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must reference manage-clients
if grep -qiE 'manage.clients' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must discuss scope or boundary
if grep -qiE 'scope|boundar|limit|restrict' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Permission model: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
