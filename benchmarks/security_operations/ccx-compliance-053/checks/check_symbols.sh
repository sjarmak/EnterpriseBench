#!/usr/bin/env bash
# check_symbols.sh — verify agent identified the correct class names
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/answer.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

python3 -c "
import json, os

answer = json.load(open(os.environ['ANSWER_FILE']))

symbols_raw = answer.get('symbols', [])
symbols = []
for s in symbols_raw:
    if isinstance(s, dict):
        symbols.append(s.get('symbol', '').lower())
    else:
        symbols.append(str(s).lower())
text = ' '.join(symbols) + ' ' + json.dumps(answer).lower()

expected = ['standardauthorizerdata', 'standardauthorizer', 'authhelper', 'authorizationresult', 'action']
found = sum(1 for sym in expected if sym.lower() in text)
score = found / len(expected)
detail = f'Identified {found}/{len(expected)} expected audit-related classes'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.4, 'detail': detail}))
"
