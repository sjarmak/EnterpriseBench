#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified null securityContext overrides as drift points
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/argo-cd/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=2

# Check 1: Agent identified securityContext as a drift point
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
text = json.dumps(points).lower()
if 'securitycontext' in text or 'security_context' in text or 'security context' in text:
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# Check 2: Agent identified null/empty value as the problematic override
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
text = json.dumps(points).lower()
if 'null' in text or 'empty' in text or 'nil' in text or 'unset' in text:
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d drift indicators"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
