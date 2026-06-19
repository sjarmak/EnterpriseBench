#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified null securityContext overrides as drift points
# Reimplemented in bash+jq+grep (no python3 in container); keyword membership over
# the lowercased JSON dump of drift_points, scoring identical to the previous
# python implementation (FOUND/TOTAL, awk %.2f, pass at FOUND>=2).
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/argo-cd/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=2

text=$(jq -c '.drift_points // []' "$REPORT" | tr '[:upper:]' '[:lower:]')
has() { printf '%s' "$text" | grep -qF -- "$1"; }

# Check 1: securitycontext / security_context / security context
if has securitycontext || has security_context || has "security context"; then
  FOUND=$((FOUND + 1))
fi

# Check 2: null / empty / nil / unset
if has null || has empty || has nil || has unset; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d drift indicators"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
