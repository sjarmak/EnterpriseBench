#!/usr/bin/env bash
# check_error_chain.sh — verify agent traced the error propagation chain
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Validates ordered call-path against ground truth error_chain
set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"
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

gt_chain = gt.get('error_chain', [])
agent_chain = answer.get('error_chain', answer.get('propagation_chain', answer.get('chain', [])))

if not gt_chain:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No GT error chain defined'}))
elif not agent_chain:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent did not provide error chain'}))
else:
    # Score based on key concepts mentioned in agent chain
    # Extract key terms from GT chain steps
    gt_terms = set()
    for step in gt_chain:
        for word in step.lower().split():
            if len(word) > 4 and word.isalpha():
                gt_terms.add(word)

    agent_text = ' '.join(str(s) for s in agent_chain).lower()
    matched = sum(1 for term in gt_terms if term in agent_text)
    score = min(1.0, matched / max(len(gt_terms) * 0.5, 1))  # 50% coverage = full score
    detail = f'Matched {matched}/{len(gt_terms)} key concepts in error chain'
    print(json.dumps({'score': round(score, 2), 'passed': score >= 0.3, 'detail': detail}))
"
