#!/usr/bin/env bash
# check_code_paths.sh — verify agent identified correct code paths
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

required = gt.get('ground_truth', gt).get('required_files', gt.get('required_files', []))
sufficient = gt.get('ground_truth', gt).get('sufficient_files', gt.get('sufficient_files', []))

agent_files_raw = answer.get('code_paths', answer.get('files', answer.get('source_files', [])))
agent_files = []
for f in (agent_files_raw if isinstance(agent_files_raw, list) else []):
    if isinstance(f, dict):
        agent_files.append(f.get('path', f.get('file', '')))
    elif isinstance(f, str):
        agent_files.append(f)

if not required:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No required files in GT'}))
elif not agent_files:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent provided no code paths'}))
else:
    def path_match(gt_path, agent_path):
        return gt_path.strip('/') == agent_path.strip('/') or agent_path.endswith(gt_path) or gt_path.endswith(agent_path)

    req_found = sum(1 for rf in required if any(path_match(rf['path'], af) for af in agent_files))
    suf_found = sum(1 for sf in sufficient if any(path_match(sf['path'], af) for af in agent_files))
    req_score = req_found / len(required)
    suf_score = suf_found / max(len(sufficient), 1)
    score = round(0.70 * req_score + 0.30 * suf_score, 2)
    print(json.dumps({'score': score, 'passed': score >= 0.3, 'detail': f'Found {req_found}/{len(required)} required, {suf_found}/{len(sufficient)} sufficient'}))
"
