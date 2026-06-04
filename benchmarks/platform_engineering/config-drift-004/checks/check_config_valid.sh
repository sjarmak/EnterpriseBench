#!/usr/bin/env bash
# Checkpoint 3: Validate corrected configuration if provided
# Null-securityContext check uses bash + jq + grep (no python3 in container). Identical
# to the previous python regex securityContext\s*:\s*null (IGNORECASE, whitespace may span
# newlines): pass (exit 0) when that pattern is absent, fail (exit 1) when present.
set -euo pipefail

export WORKSPACE="${WORKSPACE:-/workspace}"
export VALUES_FILE="$WORKSPACE/argo-cd/manifests/ha/base/redis-ha/chart/values.yaml"
export REPORT="$WORKSPACE/argo-cd/DRIFT_REPORT.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

if [[ ! -f "$VALUES_FILE" ]]; then
  printf '{"score": 1.0, "passed": true, "reason": "Corrected config not provided (optional checkpoint — skipped)"}\n'
  exit 0
fi

# Verify the corrected values.yaml does not contain null securityContext
check_no_null_securitycontext() {
  # Match securityContext followed by null with optional whitespace (incl. newlines),
  # case-insensitive — equivalent to python re 'securityContext\s*:\s*null', IGNORECASE.
  # Collapse newlines to spaces so the whitespace class can span lines, then ERE match.
  if tr '\n' ' ' < "$VALUES_FILE" | grep -qiE 'securityContext[[:space:]]*:[[:space:]]*null'; then
    # Still has null securityContext — not fixed
    return 1
  fi
  return 0
}
if check_no_null_securitycontext 2>/dev/null; then
  printf '{"score": 1.0, "passed": true, "reason": "Corrected values.yaml has no null securityContext overrides"}\n'
else
  printf '{"score": 0.25, "passed": false, "reason": "Corrected values.yaml still contains null securityContext"}\n'
fi
