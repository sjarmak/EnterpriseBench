#!/usr/bin/env bash
# check_code_paths.sh — verify agent identified correct code paths
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Compares against ground truth required_files + sufficient_files
set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"
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
import json, sys, os

gt = json.load(open(os.environ['GT_FILE']))
answer = json.load(open(os.environ['ANSWER_FILE']))

# Extract ground truth files with confidence weights
required = gt.get('ground_truth', gt).get('required_files', [])
sufficient = gt.get('ground_truth', gt).get('sufficient_files', [])

# Extract agent-identified files (flexible key names)
agent_files_raw = answer.get('code_paths', answer.get('files', answer.get('source_files', [])))
agent_files = []
for f in (agent_files_raw if isinstance(agent_files_raw, list) else []):
    if isinstance(f, dict):
        agent_files.append(f.get('path', f.get('file', '')))
    elif isinstance(f, str):
        agent_files.append(f)

if not required:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No required files in ground truth'}))
    sys.exit(0)

if not agent_files:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent provided no code paths'}))
    sys.exit(0)

def path_match(gt_path, agent_path):
    \"\"\"Check if paths match (exact or suffix match).\"\"\"
    gt_norm = gt_path.strip('/')
    ag_norm = agent_path.strip('/')
    return gt_norm == ag_norm or ag_norm.endswith(gt_norm) or gt_norm.endswith(ag_norm)

# Score required files (70% of total)
req_found = 0
req_total = len(required)
for rf in required:
    if any(path_match(rf['path'], af) for af in agent_files):
        req_found += 1

# Score sufficient files (30% of total) — bonus for finding these
suf_found = 0
suf_total = max(len(sufficient), 1)
for sf in sufficient:
    if any(path_match(sf['path'], af) for af in agent_files):
        suf_found += 1

req_score = req_found / req_total if req_total > 0 else 0.0
suf_score = suf_found / suf_total if suf_total > 0 else 0.0
score = round(0.70 * req_score + 0.30 * suf_score, 2)

detail = f'Found {req_found}/{req_total} required, {suf_found}/{len(sufficient)} sufficient files'
print(json.dumps({'score': score, 'passed': score >= 0.3, 'detail': detail}))
"
