#!/usr/bin/env bash
# Checkpoint 3: Validate corrected configuration if provided
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
if python3 -c "
import os
content = open(os.environ['VALUES_FILE']).read()
# Check that securityContext: null pattern is removed
import re
# Match securityContext followed by null (with optional whitespace)
null_pattern = re.compile(r'securityContext\s*:\s*null', re.IGNORECASE)
if null_pattern.search(content):
    # Still has null securityContext — not fixed
    exit(1)
exit(0)
" 2>/dev/null; then
  printf '{"score": 1.0, "passed": true, "reason": "Corrected values.yaml has no null securityContext overrides"}\n'
else
  printf '{"score": 0.25, "passed": false, "reason": "Corrected values.yaml still contains null securityContext"}\n'
fi
