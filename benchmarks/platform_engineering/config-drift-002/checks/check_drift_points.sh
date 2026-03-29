#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified drift points in external RabbitMQ config
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=3

# Check 1: Agent identified missing secret key parameter
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
text = json.dumps(points).lower()
if 'secret' in text and ('key' in text or 'password' in text):
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# Check 2: Agent identified unnecessary password requirement for external RabbitMQ
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
text = json.dumps(points).lower()
if 'password' in text and ('optional' in text or 'required' in text or 'unnecessary' in text or 'external' in text):
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

# Check 3: Agent identified erlangCookie or general inconsistency with external DB pattern
if python3 -c "
import json, os
report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])
text = json.dumps(points).lower()
if 'erlang' in text or 'cookie' in text or ('inconsisten' in text and ('database' in text or 'db' in text or 'rabbitmq' in text)):
    exit(0)
exit(1)
" 2>/dev/null; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d drift categories"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
