#!/usr/bin/env bash
# check_source_files.sh — verify agent identified GCC pass infrastructure files
set -euo pipefail

ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
if [[ ! -f "$ANSWER_FILE" ]]; then
    ANSWER_FILE="${WORKSPACE:-/workspace}/answer.json"
fi
export ANSWER_FILE
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

# Also check text field
agent_text = json.dumps(answer)

found = 0
for gt_f in gt_files:
    basename = gt_f.split('/')[-1]
    if any(gt_f in af or af.endswith(gt_f) for af in agent_files) or basename in agent_text:
        found += 1

score = found / len(gt_files) if gt_files else 0
detail = f'Found {found}/{len(gt_files)} required pass infrastructure files'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.5, 'detail': detail}))
"
