#!/usr/bin/env bash
# Checkpoint 3: Validate corrected configuration if provided
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
if python3 -c "
import os
helpers = open(os.environ['HELPERS']).read()
# The fix should store the password in .Values for reuse
# Look for patterns like: \$_ := set .Values or global.redis.password
if '.Values' in helpers and ('set' in helpers or 'store' in helpers or 'global' in helpers):
    # Check it still has the redis.password define
    if 'redis.password' in helpers or 'redis-password' in helpers:
        exit(0)
exit(1)
" 2>/dev/null; then
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
