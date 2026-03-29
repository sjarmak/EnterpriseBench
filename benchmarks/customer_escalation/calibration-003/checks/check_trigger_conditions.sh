#!/usr/bin/env bash
# check_trigger_conditions.sh — verify agent identified trigger conditions
set -euo pipefail

export ANSWER_FILE="${WORKSPACE}/agent_output/answer.json"
export GT_FILE="${TASK_DIR}/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

python3 -c "
import json, os

gt = json.load(open(os.environ['GT_FILE']))
answer = json.load(open(os.environ['ANSWER_FILE']))

gt_conditions = gt.get('trigger_conditions', [])
agent_conditions = answer.get('trigger_conditions', answer.get('conditions', []))

if not gt_conditions:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No trigger conditions in GT'}))
elif not agent_conditions:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent provided no trigger conditions'}))
else:
    gt_keywords = set()
    for cond in gt_conditions:
        gt_keywords.update(w.lower() for w in cond.split() if len(w) > 3)
    agent_text = ' '.join(str(c) for c in agent_conditions).lower()
    matched = sum(1 for kw in gt_keywords if kw in agent_text)
    score = round(min(matched / max(len(gt_keywords) * 0.5, 1), 1.0), 2)
    print(json.dumps({'score': score, 'passed': score >= 0.4, 'detail': f'Matched {matched} keywords from trigger conditions'}))
"
