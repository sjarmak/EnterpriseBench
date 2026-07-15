#!/usr/bin/env bash
# check_symbols.sh — verify agent identified key structs/functions
set -euo pipefail

# Read only agent_output/ — never a $WORKSPACE fallback that could pick up the
# planted prompt. The instruction is de-leaked (names none of the symbols below),
# so a match is evidence the agent read the repo, not echoed the question.
ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
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
