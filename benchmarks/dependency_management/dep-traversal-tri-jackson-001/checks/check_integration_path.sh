#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the ObjectMapper configuration chain across repos
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/DEPENDENCY_TRACE.md"
GT="${TASK_DIR:-$(dirname "$(dirname "$0")")}/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DEPENDENCY_TRACE.md not found"}\n'
  exit 0
fi

if [[ ! -f "$GT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "ground_truth.json not found"}\n'
  exit 0
fi

export REPORT_FILE="$REPORT"
export GT_FILE="$GT"

python3 -c "
import json, os

with open(os.environ['GT_FILE']) as f:
    gt = json.load(f)
with open(os.environ['REPORT_FILE']) as f:
    report_text = f.read().lower()

integration_path = gt.get('integration_path', [])
if not integration_path:
    print(json.dumps({'score': 0.0, 'passed': False, 'reason': 'No integration path in GT'}))
else:
    matched = 0
    for step in integration_path:
        keywords = [w.lower() for w in step.split() if len(w) > 4]
        if sum(1 for kw in keywords if kw in report_text) >= len(keywords) * 0.4:
            matched += 1
    score = round(matched / len(integration_path), 2)
    passed = score >= 0.4
    detail = f'Matched {matched}/{len(integration_path)} integration path steps'
    print(json.dumps({'score': score, 'passed': passed, 'reason': detail}))
"
