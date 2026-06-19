#!/usr/bin/env bash
# Checkpoint 3: Validate corrected configuration if provided
# Password-storage check uses bash + jq + grep (no python3 in container). Identical to
# the previous python: pass when the helpers file contains literal '.Values' AND one of
# 'set'/'store'/'global' AND one of 'redis.password'/'redis-password' (all case-sensitive).
set -euo pipefail

export WORKSPACE="${WORKSPACE:-/workspace}"
export CHART_DIR="$WORKSPACE/charts/bitnami/redis"
export REPORT="$WORKSPACE/charts/DRIFT_REPORT.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# Check if corrected _helpers.tpl was provided
export HELPERS="$CHART_DIR/templates/_helpers.tpl"
if [[ ! -f "$HELPERS" ]]; then
  printf '{"score": 1.0, "passed": true, "reason": "Corrected config not provided (optional checkpoint — skipped)"}\n'
  exit 0
fi

# Verify the fix stores generated password for reuse
check_password_reuse() {
  local helpers="$HELPERS"
  # The fix should store the password in .Values for reuse
  # Look for patterns like: $_ := set .Values or global.redis.password
  if grep -qF -- '.Values' "$helpers" && grep -qF -e 'set' -e 'store' -e 'global' -- "$helpers"; then
    # Check it still has the redis.password define
    if grep -qF -e 'redis.password' -e 'redis-password' -- "$helpers"; then
      return 0
    fi
  fi
  return 1
}
if check_password_reuse 2>/dev/null; then
  printf '{"score": 1.0, "passed": true, "reason": "Corrected helper stores password for reuse"}\n'
else
  # If helm is available, try template rendering
  if command -v helm &>/dev/null; then
    if helm template test-redis "$CHART_DIR" --set serviceBindings.enabled=true --dry-run 2>/dev/null | grep -q 'kind:'; then
      printf '{"score": 0.75, "passed": true, "reason": "Corrected chart templates successfully"}\n'
    else
      printf '{"score": 0.25, "passed": false, "reason": "Corrected chart fails helm template"}\n'
    fi
  else
    printf '{"score": 0.25, "passed": false, "reason": "Could not verify password storage fix in helpers"}\n'
  fi
fi
