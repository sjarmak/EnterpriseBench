#!/usr/bin/env bash
# check_ownership.sh — verify agent identified responsible code area
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

keywords = gt.get('ownership_keywords', [])
agent_text = json.dumps(answer.get('ownership', answer.get('responsible_area', ''))).lower()

if not keywords:
    print(json.dumps({'score': 1.0, 'passed': True, 'detail': 'No ownership keywords to check'}))
else:
    matched = sum(1 for kw in keywords if kw.lower() in agent_text)
    score = round(matched / len(keywords), 2)
    print(json.dumps({'score': score, 'passed': score >= 0.3, 'detail': f'Matched {matched}/{len(keywords)} ownership keywords'}))
"
