#!/usr/bin/env bash
# check_error_source.sh — verify agent identified the correct source file + function
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Compares identified files against ground truth required_files
set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found at '"$ANSWER_FILE"'"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

# Extract required file paths from ground truth
GT_FILES=$(python3 -c "
import json, sys, os
gt = json.load(open(os.environ['GT_FILE']))
for f in gt.get('required_files', []):
    print(f['path'])
")

# Extract agent-identified files from answer
AGENT_FILES=$(python3 -c "
import json, sys, os
try:
    answer = json.load(open(os.environ['ANSWER_FILE']))
    files = answer.get('source_files', answer.get('files', answer.get('error_source', {}).get('files', [])))
    if isinstance(files, list):
        for f in files:
            if isinstance(f, dict):
                print(f.get('path', f.get('file', '')))
            else:
                print(f)
    elif isinstance(files, str):
        print(files)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
")

# Score: fraction of GT required files found in agent output
python3 -c "
import json
gt_files = '''$GT_FILES'''.strip().split('\n')
agent_files = '''$AGENT_FILES'''.strip().split('\n')
gt_files = [f.strip() for f in gt_files if f.strip()]
agent_files = [f.strip() for f in agent_files if f.strip()]

if not gt_files:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No GT files'}))
else:
    found = sum(1 for gt in gt_files if any(gt in af or af.endswith(gt) for af in agent_files))
    score = found / len(gt_files)
    detail = f'Found {found}/{len(gt_files)} required source files'
    print(json.dumps({'score': round(score, 2), 'passed': score >= 0.5, 'detail': detail}))
"
