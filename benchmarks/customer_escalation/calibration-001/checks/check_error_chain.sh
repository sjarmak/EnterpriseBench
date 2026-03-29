#!/usr/bin/env bash
# check_error_chain.sh — verify agent traced the error propagation chain
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

gt_chain = gt.get('error_chain', [])
agent_chain = answer.get('error_chain', answer.get('chain', answer.get('propagation', [])))

if not gt_chain:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No error chain in GT'}))
elif not agent_chain:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent provided no error chain'}))
else:
    # Check keyword overlap between GT chain steps and agent chain
    gt_keywords = set()
    for step in gt_chain:
        gt_keywords.update(w.lower() for w in step.split() if len(w) > 3)
    agent_text = ' '.join(str(s) for s in agent_chain).lower()
    matched = sum(1 for kw in gt_keywords if kw in agent_text)
    score = round(min(matched / max(len(gt_keywords) * 0.5, 1), 1.0), 2)
    print(json.dumps({'score': score, 'passed': score >= 0.4, 'detail': f'Matched {matched} keywords from error chain'}))
"
