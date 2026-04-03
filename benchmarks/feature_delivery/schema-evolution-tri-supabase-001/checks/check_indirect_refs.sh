#!/usr/bin/env bash
# check_indirect_refs.sh — verify agent traces indirect schema dependencies
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

# Check for impact chain concepts
gt_chain = gt.get('impact_chain', [])
answer_text = json.dumps(answer).lower()

gt_terms = set()
for step in gt_chain:
    for word in step.lower().split():
        if len(word) > 4 and word.isalpha():
            gt_terms.add(word)

matched = sum(1 for term in gt_terms if term in answer_text)
score = min(1.0, matched / max(len(gt_terms) * 0.4, 1))
passed = score >= 0.3

detail = f'Matched {matched}/{len(gt_terms)} impact chain concepts'
print(json.dumps({'score': round(score, 2), 'passed': passed, 'detail': detail}))
"
