#!/usr/bin/env bash
# Checkpoint 2: Verify agent correctly determined that null overrides should be removed
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/argo-cd/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=2

# Check 1: Agent recommends removing the null override or letting upstream defaults apply
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
text = json.dumps(report).lower()
if 'remove' in text or 'delete' in text or 'omit' in text or 'upstream default' in text or 'let.*default' in text:
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# Check 2: Agent identified Helm 3.17.1 version sensitivity
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
text = json.dumps(report).lower()
if '3.17' in text or 'helm version' in text or 'strict' in text or 'validation' in text or 'tighten' in text:
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 1 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Expected value correctness: %d/%d checks passed"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
