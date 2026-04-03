#!/usr/bin/env bash
# Checkpoint 2: Verify agent determined correct expected values per drift point
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# Check that agent correctly identifies the expected value for serflan-udp should reference serfLAN
export FOUND=0
export TOTAL=2

# serflan-udp should use containerPorts.serfLAN
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
for p in points:
    key = (p.get('key', '') + p.get('file', '')).lower()
    expected = p.get('expected', '').lower()
    if 'serflan' in key and 'serflan' in expected:
        exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# serfwan-udp should use containerPorts.serfWAN
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
for p in points:
    key = (p.get('key', '') + p.get('file', '')).lower()
    expected = p.get('expected', '').lower()
    if 'serfwan' in key and 'serfwan' in expected:
        exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 1 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Correct expected values for %d/%d drift points"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
