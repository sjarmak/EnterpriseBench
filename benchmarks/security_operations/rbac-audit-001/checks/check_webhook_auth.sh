#!/usr/bin/env bash
# Checkpoint 3: Verify agent describes the webhook authorize() path
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Must reference webhook RBAC file
if grep -qiE 'webhook.*rbac|rbac\.go|webhooks/pkg' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must mention authorize function
if grep -qiE 'authorize\(\)|authorize.*func' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Must identify that webhook checks new tier only (not old)
if grep -qiE 'new.*tier|destination.*tier|target.*tier|updated.*tier' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Webhook auth analysis: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
