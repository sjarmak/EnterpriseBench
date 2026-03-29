#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified drift points (set precision/recall)
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# Expected drift points: serflan-udp and serfwan-udp port mismatches
export FOUND=0
export TOTAL=2

# Check if agent identified the serflan-udp port drift (serfLAN value used where serfWAN should be, or vice versa)
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
for p in points:
    f = p.get('file', '') + p.get('key', '')
    if 'serflan' in f.lower() or 'serf_lan' in f.lower() or 'serfLAN' in f:
        exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# Check if agent identified the serfwan-udp port drift
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
for p in points:
    f = p.get('file', '') + p.get('key', '')
    if 'serfwan' in f.lower() or 'serf_wan' in f.lower() or 'serfWAN' in f:
        exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d drift points"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
