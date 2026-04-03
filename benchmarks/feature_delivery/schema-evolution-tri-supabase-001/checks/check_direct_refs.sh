#!/usr/bin/env bash
# check_direct_refs.sh — verify agent finds direct references in PostgREST and GoTrue
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

gt_files = gt.get('required_files', []) + gt.get('sufficient_files', [])
postgrest_files = [f['path'] for f in gt_files if f.get('repo') == 'postgrest']
gotrue_files = [f['path'] for f in gt_files if f.get('repo') == 'gotrue']

answer_text = json.dumps(answer).lower()

postgrest_found = sum(1 for f in postgrest_files if f.lower() in answer_text or f.split('/')[-1].lower() in answer_text)
gotrue_found = sum(1 for f in gotrue_files if f.lower() in answer_text or f.split('/')[-1].lower() in answer_text)

total_expected = len(postgrest_files) + len(gotrue_files)
total_found = postgrest_found + gotrue_found
score = round(total_found / max(total_expected, 1), 2)
passed = postgrest_found >= 1 and gotrue_found >= 1

detail = f'PostgREST: {postgrest_found}/{len(postgrest_files)}, GoTrue: {gotrue_found}/{len(gotrue_files)}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
