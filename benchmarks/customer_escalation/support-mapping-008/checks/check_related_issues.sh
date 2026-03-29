#!/usr/bin/env bash
# check_related_issues.sh — verify agent identified related issues and documentation
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Checks for references to related docs, PRs, configuration guides
set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

python3 -c "
import json, sys, os

gt = json.load(open(os.environ['GT_FILE']))
answer = json.load(open(os.environ['ANSWER_FILE']))

# Get related references from ground truth
related_refs = gt.get('related_references', [])

# Fallback: use sufficient_files paths as references
if not related_refs:
    sufficient = gt.get('ground_truth', gt).get('sufficient_files', [])
    related_refs = [sf['path'] for sf in sufficient]

if not related_refs:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No related references in ground truth'}))
    sys.exit(0)

# Extract agent references (flexible key names)
refs_raw = answer.get('related_issues', answer.get('references', answer.get('related', answer.get('docs', []))))
agent_refs = []
if isinstance(refs_raw, list):
    for r in refs_raw:
        if isinstance(r, dict):
            agent_refs.append(r.get('reference', r.get('path', r.get('url', r.get('title', '')))))
        elif isinstance(r, str):
            agent_refs.append(r)
elif isinstance(refs_raw, str):
    agent_refs.append(refs_raw)

if not agent_refs:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent provided no related references'}))
    sys.exit(0)

def ref_match(gt_ref, agent_ref):
    \"\"\"Fuzzy match: basename or key segments overlap.\"\"\"
    gt_parts = set(gt_ref.lower().replace('/', ' ').replace('.', ' ').split())
    ag_parts = set(agent_ref.lower().replace('/', ' ').replace('.', ' ').split())
    # Remove very common words
    stop = {'src', 'lib', 'the', 'and', 'for', 'main', 'java', 'py', 'go', 'ts', 'js', 'rs', 'cpp', 'h'}
    gt_sig = gt_parts - stop
    ag_sig = ag_parts - stop
    if not gt_sig:
        return False
    overlap = len(gt_sig & ag_sig) / len(gt_sig)
    return overlap >= 0.5

found = sum(1 for ref in related_refs if any(ref_match(ref, ar) for ar in agent_refs))
score = round(found / len(related_refs), 2)
detail = f'Matched {found}/{len(related_refs)} related references'
print(json.dumps({'score': score, 'passed': score >= 0.3, 'detail': detail}))
"
