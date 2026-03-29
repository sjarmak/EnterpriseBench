#!/usr/bin/env bash
# check_dead_code.sh — verify dead code identification
set -euo pipefail

REPORT="${WORKSPACE}/agent_output/answer.json"
GT="${TASK_DIR}/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 0
fi

if [[ ! -f "$GT" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "Ground truth not found"}'
    exit 0
fi

python3 -c "
import json, sys

with open('${REPORT}') as f:
    answer = json.load(f)
with open('${GT}') as f:
    gt = json.load(f)

claimed = answer.get('dead_code', answer.get('dead_exports', []))
gt_dead = gt.get('dead_code', [])
gt_live = gt.get('live_code', [])

def normalize(items):
    result = set()
    for e in items:
        if isinstance(e, dict):
            result.add((e.get('file', ''), e.get('symbol', '')))
        elif isinstance(e, str):
            result.add(('', e))
    return result

claimed_set = normalize(claimed)
dead_set = normalize(gt_dead)
live_set = normalize(gt_live)

tp = len(claimed_set & dead_set)
fp = len(claimed_set & live_set)
fn = len(dead_set - claimed_set)

precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

if precision + recall > 0:
    f_score = (1.25 * precision * recall) / (0.25 * precision + recall)
else:
    f_score = 0.0

score = f_score
if precision < 0.9:
    score *= 0.7

detail = f'precision={precision:.2f} recall={recall:.2f} TP={tp} FP={fp} FN={fn}'
print(json.dumps({'score': round(score, 4), 'passed': score >= 0.3, 'detail': detail}))
"
