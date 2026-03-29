#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified password drift across template includes
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=3

# Check 1: Agent identified that the password helper produces different values
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
text = json.dumps(points).lower()
if 'password' in text and ('different' in text or 'random' in text or 'regenerat' in text or 're-evaluat' in text or 'mismatch' in text):
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# Check 2: Agent identified multiple consuming templates (at least 2 different files)
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
files = set()
for p in points:
    f = p.get('file', '')
    if f:
        files.add(f)
if len(files) >= 2:
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# Check 3: Agent mentioned the _helpers.tpl redis.password helper
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
text = json.dumps(report).lower()
if 'helper' in text or '_helpers' in text or 'redis.password' in text or 'include' in text:
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d drift indicators"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
