#!/usr/bin/env bash
# check_direct_consumers.sh — verify agent finds Istio and go-control-plane xDS implementations
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

# Check for Istio references
istio_files = [f['path'] for f in gt.get('required_files', []) + gt.get('sufficient_files', []) if f.get('repo') == 'istio']
istio_found = sum(1 for f in istio_files if f.lower() in answer_text or f.split('/')[-1].lower() in answer_text)
has_istio = istio_found > 0 or 'pilot' in answer_text or 'istio' in answer_text

# Check for go-control-plane references
gcp_files = [f['path'] for f in gt.get('required_files', []) + gt.get('sufficient_files', []) if f.get('repo') == 'go-control-plane']
gcp_found = sum(1 for f in gcp_files if f.lower() in answer_text or f.split('/')[-1].lower() in answer_text)
has_gcp = gcp_found > 0 or 'control-plane' in answer_text or 'snapshot' in answer_text

repos_covered = sum([has_istio, has_gcp])
score = round(repos_covered / 2.0, 2)
passed = has_istio and has_gcp

detail = f'Istio refs: {has_istio} ({istio_found} files), go-control-plane refs: {has_gcp} ({gcp_found} files)'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
