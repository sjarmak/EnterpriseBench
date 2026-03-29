#!/usr/bin/env bash
# check_severity.sh — verify agent correctly assessed severity
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Checks severity assessment against expected severity level
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

expected_severity = gt.get('expected_severity', '').lower()

if not expected_severity:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No expected severity in ground truth'}))
    sys.exit(0)

# Extract agent severity (flexible key names)
sev = answer.get('severity', answer.get('impact', answer.get('priority', '')))
if isinstance(sev, dict):
    agent_severity = sev.get('level', sev.get('severity', sev.get('rating', ''))).lower()
    agent_rationale = sev.get('rationale', sev.get('reason', '')).lower()
elif isinstance(sev, str):
    agent_severity = sev.lower()
    agent_rationale = ''
else:
    agent_severity = str(sev).lower()
    agent_rationale = ''

if not agent_severity.strip():
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'Agent provided no severity assessment'}))
    sys.exit(0)

# Severity level mapping for distance scoring
LEVELS = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
expected_idx = LEVELS.get(expected_severity, -1)

# Find agent severity level
agent_idx = -1
for level, idx in LEVELS.items():
    if level in agent_severity:
        agent_idx = idx
        break

if expected_idx < 0 or agent_idx < 0:
    # Can't parse — check for keyword overlap
    if expected_severity in agent_severity:
        score = 1.0
    else:
        score = 0.0
else:
    distance = abs(expected_idx - agent_idx)
    score = max(0.0, 1.0 - distance * 0.4)

score = round(score, 2)
detail = f'Expected: {expected_severity}, Agent: {agent_severity} (score={score})'
print(json.dumps({'score': score, 'passed': score >= 0.3, 'detail': detail}))
"
