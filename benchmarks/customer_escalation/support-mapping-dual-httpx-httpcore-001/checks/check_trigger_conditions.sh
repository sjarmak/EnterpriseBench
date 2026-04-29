#!/usr/bin/env bash
# check_trigger_conditions.sh -- semantic conditions: agent identified the conditions producing ReadTimeout despite timeout=None

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
conditions = gt.get('trigger_conditions', [])

found = 0
for cond in conditions:
    keywords = [w for w in cond.lower().split() if len(w) > 5][:3]
    if all(kw in answer_text for kw in keywords):
        found += 1

score = found / len(conditions) if conditions else 0.0
detail = f'Matched {found}/{len(conditions)} trigger conditions'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.5, 'detail': detail}))
"
