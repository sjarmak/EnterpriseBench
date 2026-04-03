#!/usr/bin/env bash
# check_transitive_impact.sh — verify agent traces xDS contract divergence across repos
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

gt_terms = set()
for step in gt_chain:
    for word in step.lower().split():
        if len(word) > 4 and word.isalpha():
            gt_terms.add(word)

matched = sum(1 for term in gt_terms if term in answer_text)

# Check for xDS-specific protocol concepts
xds_concepts = ['version', 'nonce', 'type_url', 'incremental', 'state-of-the-world', 'sotw', 'delta', 'cds', 'eds', 'lds', 'rds']
xds_matched = sum(1 for c in xds_concepts if c in answer_text)

chain_score = min(1.0, matched / max(len(gt_terms) * 0.4, 1))
xds_score = min(1.0, xds_matched / 4.0)
score = round(chain_score * 0.5 + xds_score * 0.5, 2)
passed = score >= 0.3

detail = f'Chain concepts: {matched}/{len(gt_terms)}, xDS concepts: {xds_matched}/{len(xds_concepts)}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
