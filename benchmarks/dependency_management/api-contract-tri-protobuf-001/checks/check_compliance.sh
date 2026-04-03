#!/usr/bin/env bash
# check_compliance.sh — verify agent identifies contract compliance issues
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

gt_chain = gt.get('contract_chain', [])
answer_text = json.dumps(answer).lower()

# Extract key terms from contract chain
gt_terms = set()
for step in gt_chain:
    for word in step.lower().split():
        if len(word) > 4 and word.isalpha():
            gt_terms.add(word)

matched = sum(1 for term in gt_terms if term in answer_text)
score = min(1.0, matched / max(len(gt_terms) * 0.4, 1))

# Check for compliance-specific concepts
compliance_terms = ['serializ', 'json', 'contract', 'drift', 'mismatch', 'breaking', 'compat']
comp_matched = sum(1 for c in compliance_terms if c in answer_text)
comp_score = min(1.0, comp_matched / 3.0)

final_score = round(score * 0.6 + comp_score * 0.4, 2)
passed = final_score >= 0.3

detail = f'Chain concepts: {matched}/{len(gt_terms)}, compliance terms: {comp_matched}/{len(compliance_terms)}'
print(json.dumps({'score': final_score, 'passed': passed, 'detail': detail}))
"
