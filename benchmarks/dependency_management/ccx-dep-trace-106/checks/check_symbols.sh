#!/usr/bin/env bash
# check_symbols.sh — verify agent identified key structs/functions
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

expected = ['opt_pass', 'pass_manager', 'execute_pass_list', 'tree_ssa_dce', 'passes.def']
found = sum(1 for sym in expected if sym.replace('_', '') in text.replace('_', '') or sym in text)
score = found / len(expected)
detail = f'Identified {found}/{len(expected)} expected pass registration symbols'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.4, 'detail': detail}))
"
