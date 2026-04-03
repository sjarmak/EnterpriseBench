#!/usr/bin/env bash
# Checkpoint 3: Verify agent identifies the escalation path
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must describe privilege escalation
if grep -qiE 'privilege.*escalat|escalat.*privilege|elevat.*permission' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must reference manage-clients as the entry point
if grep -qiE 'manage.clients.*escalat|manage.clients.*beyond|manage.clients.*broader' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must reference Admin Permissions being enabled
if grep -qiE 'admin.*permission.*enable|enable.*admin.*permission|realm.*admin' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Escalation path: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
