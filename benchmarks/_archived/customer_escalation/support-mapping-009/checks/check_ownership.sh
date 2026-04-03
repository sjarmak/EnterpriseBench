#!/usr/bin/env bash
# check_ownership.sh — verify agent identified correct code owners or subsystem
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Checks for correct ownership attribution against ground truth keywords
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

# Get ownership keywords from ground truth
ownership_kw = gt.get('ownership_keywords', [])

if not ownership_kw:
    # Fallback: extract from required_files rationale
    required = gt.get('ground_truth', gt).get('required_files', [])
    for rf in required:
        rat = rf.get('rationale', '').lower()
        for word in rat.split():
            if len(word) > 4 and word.isalpha():
                ownership_kw.append(word)
    ownership_kw = list(set(ownership_kw))[:10]

if not ownership_kw:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No ownership keywords in ground truth'}))
    sys.exit(0)

# Extract agent ownership text (flexible key names)
ownership = answer.get('ownership', answer.get('owners', answer.get('subsystem', '')))
if isinstance(ownership, dict):
    ownership_text = ' '.join(str(v) for v in ownership.values()).lower()
elif isinstance(ownership, list):
    ownership_text = ' '.join(str(v) for v in ownership).lower()
else:
    ownership_text = str(ownership).lower()

if not ownership_text.strip():
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent provided no ownership info'}))
    sys.exit(0)

# Score based on keyword matches
matched = sum(1 for kw in ownership_kw if kw.lower().replace('-', ' ') in ownership_text or kw.lower().replace('-', '') in ownership_text.replace(' ', ''))
score = round(min(1.0, matched / max(len(ownership_kw) * 0.4, 1)), 2)
detail = f'Matched {matched}/{len(ownership_kw)} ownership keywords'
print(json.dumps({'score': score, 'passed': score >= 0.3, 'detail': detail}))
"
