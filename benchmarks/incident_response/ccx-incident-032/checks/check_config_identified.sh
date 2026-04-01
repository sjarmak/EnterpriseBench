#!/usr/bin/env bash
# check_config_identified.sh — verify agent identified circuit breaker config
set -euo pipefail

ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
if [[ ! -f "$ANSWER_FILE" ]]; then
    ANSWER_FILE="${WORKSPACE:-/workspace}/answer.json"
fi
export ANSWER_FILE

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

python3 -c "
import json, os

answer = json.load(open(os.environ['ANSWER_FILE']))
text = json.dumps(answer).lower()

keywords = ['circuit_breaker', 'circuit breaker', 'max_connections', 'max_pending_requests', 'thresholds']
found = sum(1 for kw in keywords if kw in text)
score = min(1.0, found / 2.0)
detail = f'Found {found}/{len(keywords)} circuit breaker config keywords'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.5, 'detail': detail}))
"
