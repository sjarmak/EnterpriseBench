#!/usr/bin/env bash
# check_source_files.sh — verify agent identified the core routing hierarchy files
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 0
fi

export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

python3 -c "
import json, os

gt = json.load(open(os.environ['GT_FILE']))
gt_files = [f['path'] for f in gt.get('required_files', [])]

answer_file = os.environ['ANSWER_FILE']
if answer_file.endswith('.json'):
    try:
        answer = json.load(open(answer_file))
        agent_files_raw = answer.get('files', [])
        agent_files = []
        for f in agent_files_raw:
            if isinstance(f, dict):
                agent_files.append(f.get('path', ''))
            else:
                agent_files.append(str(f))
        agent_text = json.dumps(answer)
    except Exception:
        agent_text = open(answer_file).read()
        agent_files = []
else:
    agent_text = open(answer_file).read()
    agent_files = []

# Match against both explicit file list and text content
found = 0
for gt_f in gt_files:
    basename = gt_f.split('/')[-1]
    if any(gt_f in af or af.endswith(gt_f) for af in agent_files) or basename in agent_text:
        found += 1

score = found / len(gt_files) if gt_files else 0
detail = f'Found {found}/{len(gt_files)} required hierarchy files'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.5, 'detail': detail}))
"
