#!/usr/bin/env bash
# Checkpoint 2: Verify agent correctly identified root cause as Helm include re-evaluation
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=2

# Check 1: Agent identified Helm include re-evaluation as root cause
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
root_cause = report.get('root_cause', '')
text = (root_cause + json.dumps(report.get('drift_points', []))).lower()
# Must mention that include/template re-evaluates or generates new values each time
if ('re-evaluat' in text or 'regenerat' in text or 're-run' in text or 'each time' in text or 'every call' in text or 'each call' in text or 'non-idempotent' in text or 'not idempotent' in text):
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# Check 2: Agent identified that password should be consistent/stored/reused
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
text = json.dumps(report).lower()
if ('consistent' in text or 'store' in text or 'reuse' in text or 'single' in text or 'same password' in text or 'once' in text):
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 1 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Root cause correctness: %d/%d checks passed"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
