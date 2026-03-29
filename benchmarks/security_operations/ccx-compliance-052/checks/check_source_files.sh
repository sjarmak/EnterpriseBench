#!/usr/bin/env bash
# check_source_files.sh — verify agent identified access log implementation files
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

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

gt_files = [f['path'] for f in gt.get('required_files', [])]
agent_files_raw = answer.get('files', [])
agent_files = []
for f in agent_files_raw:
    if isinstance(f, dict):
        agent_files.append(f.get('path', ''))
    else:
        agent_files.append(str(f))

if not gt_files:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No GT files'}))
else:
    found = sum(1 for gt_f in gt_files if any(gt_f in af or af.endswith(gt_f) for af in agent_files))
    score = found / len(gt_files)
    detail = f'Found {found}/{len(gt_files)} required source files'
    print(json.dumps({'score': round(score, 2), 'passed': score >= 0.5, 'detail': detail}))
"
