#!/usr/bin/env bash
# check_drift_points.sh — verify agent identified drift points
set -euo pipefail

export REPORT="${WORKSPACE}/agent_output/answer.json"
export GT_FILE="${TASK_DIR}/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 0
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 0
fi

python3 -c "
import json, os

with open(os.environ['REPORT']) as f:
    answer = json.load(f)
with open(os.environ['GT_FILE']) as f:
    gt = json.load(f)

gt_points = gt.get('drift_points', [])
agent_points = answer.get('drift_points', [])
agent_text = json.dumps(agent_points).lower()

found = 0
for gp in gt_points:
    key = gp.get('key', '').lower()
    if key and key in agent_text:
        found += 1

total = max(len(gt_points), 1)
score = round(found / total, 2)
print(json.dumps({'score': score, 'passed': score >= 0.5, 'detail': f'Found {found}/{total} drift points'}))
"
