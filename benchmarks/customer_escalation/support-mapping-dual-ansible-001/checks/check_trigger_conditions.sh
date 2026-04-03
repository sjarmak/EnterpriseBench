#!/usr/bin/env bash
# check_trigger_conditions.sh — verify agent identified trigger conditions
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

python3 -c "
import json
import os

gt = json.load(open(os.environ['GT_FILE']))
answer = json.load(open(os.environ['ANSWER_FILE']))

gt_conditions = gt.get('trigger_conditions', [])
agent_conditions = answer.get('trigger_conditions', answer.get('conditions', answer.get('triggers', [])))

if not gt_conditions:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No GT trigger conditions defined'}))
elif not agent_conditions:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent did not identify trigger conditions'}))
else:
    agent_text = ' '.join(str(c) for c in agent_conditions).lower()
    matched = 0
    for condition in gt_conditions:
        keywords = [w.lower() for w in condition.split() if len(w) > 3]
        if any(kw in agent_text for kw in keywords):
            matched += 1
    score = matched / len(gt_conditions)
    detail = f'Matched {matched}/{len(gt_conditions)} trigger conditions'
    print(json.dumps({'score': round(score, 2), 'passed': score >= 0.3, 'detail': detail}))
"
