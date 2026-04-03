#!/usr/bin/env bash
# check_contract_source.sh — verify agent identifies well-known type definitions
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

gt_files = [f['path'] for f in gt.get('required_files', []) + gt.get('sufficient_files', []) if f.get('repo') == 'protobuf']
answer_text = json.dumps(answer).lower()

found = sum(1 for f in gt_files if f.lower() in answer_text or f.split('/')[-1].lower() in answer_text)

# Check for well-known type keywords
wkt = ['timestamp', 'duration', 'fieldmask', 'struct', 'any.proto']
wkt_found = sum(1 for w in wkt if w in answer_text)

file_score = found / max(len(gt_files), 1)
wkt_score = min(1.0, wkt_found / 3.0)
score = round(file_score * 0.6 + wkt_score * 0.4, 2)
passed = found >= 1 and wkt_found >= 2

detail = f'Protobuf files: {found}/{len(gt_files)}, WKT keywords: {wkt_found}/{len(wkt)}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
