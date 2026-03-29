#!/usr/bin/env bash
# check_evidence.sh — validate reasoning quality for dead code claims
set -euo pipefail

REPORT="${WORKSPACE}/agent_output/answer.json"

if [[ ! -f "$REPORT" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 0
fi

python3 -c "
import json

with open('${REPORT}') as f:
    answer = json.load(f)

items = answer.get('dead_code', answer.get('dead_exports', []))
if not items:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No dead code items found'}))
else:
    with_evidence = sum(1 for it in items if isinstance(it, dict) and it.get('evidence', ''))
    score = round(with_evidence / len(items), 2)
    print(json.dumps({'score': score, 'passed': score >= 0.5, 'detail': f'{with_evidence}/{len(items)} items have evidence'}))
"
