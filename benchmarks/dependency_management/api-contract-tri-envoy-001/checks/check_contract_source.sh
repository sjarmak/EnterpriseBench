#!/usr/bin/env bash
# check_contract_source.sh — verify agent identifies xDS API definitions in Envoy
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

python3 -c "
import json, os

gt = json.load(open(os.environ['GT_FILE']))
answer = json.load(open(os.environ['ANSWER_FILE']))

gt_files = [f['path'] for f in gt.get('required_files', []) + gt.get('sufficient_files', []) if f.get('repo') == 'envoy']
answer_text = json.dumps(answer).lower()

found = sum(1 for f in gt_files if f.lower() in answer_text or f.split('/')[-1].lower() in answer_text)

keywords = ['xds', 'discovery', 'subscription', 'grpc', 'ads', 'config']
kw_found = sum(1 for kw in keywords if kw in answer_text)

file_score = found / max(len(gt_files), 1)
kw_score = min(1.0, kw_found / 3.0)
score = round(file_score * 0.6 + kw_score * 0.4, 2)
passed = found >= 1 and kw_found >= 2

detail = f'Envoy files: {found}/{len(gt_files)}, keywords: {kw_found}/{len(keywords)}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
