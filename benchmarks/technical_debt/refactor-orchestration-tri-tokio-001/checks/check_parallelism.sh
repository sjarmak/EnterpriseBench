#!/usr/bin/env bash
# Checkpoint 3: Verify agent correctly identifies parallelizable steps
set -euo pipefail

ANSWER="${WORKSPACE:-/workspace}/REFACTOR_PLAN.md"
GT="${TASK_DIR:-$(dirname "$(dirname "$0")")}/ground_truth.json"

if [[ ! -f "$ANSWER" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "REFACTOR_PLAN.md not found"}\n'
  exit 0
fi

if [[ ! -f "$GT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "ground_truth.json not found"}\n'
  exit 0
fi

export ANSWER_FILE="$ANSWER"
export GT_FILE="$GT"

python3 -c "
import json, os

with open(os.environ['GT_FILE']) as f:
    gt = json.load(f)
with open(os.environ['ANSWER_FILE']) as f:
    answer_text = f.read().lower()

parallel_steps = gt.get('parallelizable_steps', [])

mentions_parallel = any(term in answer_text for term in ['parallel', 'concurrent', 'simultaneous', 'independent'])

if not parallel_steps:
    if any(term in answer_text for term in ['sequential', 'serial', 'no parallel', 'cannot.*parallel', 'depends on']):
        score = 1.0
        detail = 'Correctly identified no parallelizable steps (sequential chain)'
    elif mentions_parallel:
        score = 0.3
        detail = 'Mentions parallelism but chain is fully sequential'
    else:
        score = 0.5
        detail = 'Did not explicitly address parallelism'
    passed = score >= 0.5
else:
    if mentions_parallel:
        score = 0.8
        detail = 'Agent addresses parallelism opportunities'
    else:
        score = 0.2
        detail = 'Agent did not identify parallelism opportunities'
    passed = score >= 0.5

print(json.dumps({'score': round(score, 2), 'passed': passed, 'reason': detail}))
"
