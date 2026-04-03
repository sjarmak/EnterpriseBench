#!/usr/bin/env bash
# check_direct_consumers.sh — verify agent finds gRPC and googleapis consumers
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

answer_text = json.dumps(answer).lower()

# Check for gRPC consumer references
grpc_files = [f['path'] for f in gt.get('required_files', []) + gt.get('sufficient_files', []) if f.get('repo') == 'grpc']
grpc_found = sum(1 for f in grpc_files if f.lower() in answer_text or f.split('/')[-1].lower() in answer_text)
has_grpc = grpc_found > 0 or 'grpc' in answer_text

# Check for googleapis consumer references
gapi_files = [f['path'] for f in gt.get('required_files', []) + gt.get('sufficient_files', []) if f.get('repo') == 'googleapis']
gapi_found = sum(1 for f in gapi_files if f.lower() in answer_text or f.split('/')[-1].lower() in answer_text)
has_gapi = gapi_found > 0 or 'googleapis' in answer_text

repos_covered = sum([has_grpc, has_gapi])
score = round(repos_covered / 2.0, 2)
passed = has_grpc and has_gapi

detail = f'gRPC refs: {has_grpc} ({grpc_found} files), googleapis refs: {has_gapi} ({gapi_found} files)'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
