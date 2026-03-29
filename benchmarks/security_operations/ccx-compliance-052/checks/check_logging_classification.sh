#!/usr/bin/env bash
# check_logging_classification.sh — verify agent classified structured vs unstructured logging
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/answer.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

python3 -c "
import json, os

answer = json.load(open(os.environ['ANSWER_FILE']))
text = json.dumps(answer).lower()

# Must discuss structured/JSON vs unstructured/text logging
keywords = ['structured', 'json', 'unstructured', 'text logging', 'access_log']
found = sum(1 for kw in keywords if kw in text)
score = min(1.0, found / 3.0)
detail = f'Found {found}/{len(keywords)} logging classification keywords'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.3, 'detail': detail}))
"
