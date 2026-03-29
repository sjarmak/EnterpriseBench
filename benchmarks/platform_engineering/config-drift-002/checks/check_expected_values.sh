#!/usr/bin/env bash
# Checkpoint 2: Verify agent determined correct expected values for each drift point
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=2

# Check 1: Agent correctly identifies that password should be optional when using existing secret
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
for p in points:
    expected = p.get('expected', '').lower()
    key = p.get('key', '').lower()
    if ('optional' in expected or 'not required' in expected or 'not mandatory' in expected) and 'password' in (key + expected):
        exit(0)
    if 'existing' in expected and 'secret' in expected:
        exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# Check 2: Agent identifies the need for configurable secret key name
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
for p in points:
    expected = p.get('expected', '').lower()
    key = p.get('key', '').lower()
    combined = expected + ' ' + key
    if 'key' in combined and 'secret' in combined:
        exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 1 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Correct expected values for %d/%d key drift points"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
