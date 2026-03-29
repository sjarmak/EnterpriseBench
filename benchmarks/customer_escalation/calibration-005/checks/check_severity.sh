#!/usr/bin/env bash
# check_severity.sh — verify agent assessed severity correctly
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

expected = gt.get('expected_severity', 'medium').lower()
actual = str(answer.get('severity', answer.get('impact', ''))).lower()

if expected in actual:
    print(json.dumps({'score': 1.0, 'passed': True, 'detail': f'Severity matches: {expected}'}))
elif actual:
    print(json.dumps({'score': 0.3, 'passed': False, 'detail': f'Expected {expected}, got {actual}'}))
else:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No severity assessment provided'}))
"
