#!/usr/bin/env bash
# check_drift_analysis.sh — verify agent identifies contract drift between FastAPI and httpx
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

# Check for drift-related concepts
drift_concepts = ['none', 'missing', 'optional', 'default', 'nested', 'union', 'serializ', 'pydantic', '422', 'content-type']
matched = sum(1 for c in drift_concepts if c in answer_text)

# Check both repos are referenced in drift analysis
has_fastapi = 'fastapi' in answer_text
has_httpx = 'httpx' in answer_text

concept_score = min(1.0, matched / 4.0)
repo_score = (1.0 if has_fastapi else 0.0) * 0.5 + (1.0 if has_httpx else 0.0) * 0.5
score = round(concept_score * 0.6 + repo_score * 0.4, 2)
passed = matched >= 3 and has_fastapi and has_httpx

detail = f'Drift concepts: {matched}/{len(drift_concepts)}, FastAPI: {has_fastapi}, httpx: {has_httpx}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
