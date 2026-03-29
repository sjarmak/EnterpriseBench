#!/usr/bin/env bash
# check_error_source.sh — verify agent identified the correct source file + function
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

required = gt.get('required_files', [])
agent_files_raw = answer.get('source_files', answer.get('files', answer.get('error_source', {}).get('files', [])))
agent_files = []
for f in (agent_files_raw if isinstance(agent_files_raw, list) else []):
    if isinstance(f, dict):
        agent_files.append(f.get('path', f.get('file', '')))
    elif isinstance(f, str):
        agent_files.append(f)

if not required:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No required files in GT'}))
elif not agent_files:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent provided no files'}))
else:
    found = sum(1 for gt_f in required if any(gt_f['path'] in af or af.endswith(gt_f['path']) for af in agent_files))
    score = round(found / len(required), 2)
    print(json.dumps({'score': score, 'passed': score >= 0.5, 'detail': f'Found {found}/{len(required)} required source files'}))
"
