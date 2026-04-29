#!/usr/bin/env bash
# check_error_chain.sh -- semantic chain matching: agent traces full timeout marshaling chain

set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

python3 -c "
import json, os

answer = json.load(open(os.environ['ANSWER_FILE']))
gt = json.load(open(os.environ['GT_FILE']))

answer_text = json.dumps(answer).lower()
gt_chain = gt.get('error_chain', [])

found = 0
for step in gt_chain:
    keywords = [w for w in step.lower().split() if len(w) > 5][:3]
    if all(kw in answer_text for kw in keywords):
        found += 1

score = found / len(gt_chain) if gt_chain else 0.0
detail = f'Matched {found}/{len(gt_chain)} timeout chain steps'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.5, 'detail': detail}))
"
