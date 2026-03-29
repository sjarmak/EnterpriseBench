#!/usr/bin/env bash
# check_config_valid.sh — validate corrected config if provided
set -euo pipefail

export REPORT="${WORKSPACE}/agent_output/answer.json"

if [[ ! -f "$REPORT" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 0
fi

python3 -c "
import json

with open('${REPORT}') as f:
    answer = json.load(f)

# Check if agent provided override chain or fix suggestion
has_chain = bool(answer.get('override_chain', answer.get('drift_points', [])))
has_fix = bool(answer.get('fix', answer.get('corrected_config', '')))

if has_chain and has_fix:
    print(json.dumps({'score': 1.0, 'passed': True, 'detail': 'Override chain and fix provided'}))
elif has_chain:
    print(json.dumps({'score': 0.6, 'passed': True, 'detail': 'Override chain provided, no fix'}))
elif has_fix:
    print(json.dumps({'score': 0.5, 'passed': True, 'detail': 'Fix provided, no override chain'}))
else:
    print(json.dumps({'score': 0.2, 'passed': False, 'detail': 'No override chain or fix provided'}))
"
