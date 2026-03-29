#!/usr/bin/env bash
# check_fixes_proposed.sh — verify agent proposed unified diff patches
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

export REVIEW_FILE="$WORKSPACE/agent_output/answer.json"
if [[ ! -f "$REVIEW_FILE" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
    exit 0
fi

python3 -c "
import json, os
review = json.load(open(os.environ['REVIEW_FILE']))
if not isinstance(review, list):
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'review.json is not a JSON array'}))
else:
    patches = [d for d in review if d.get('fix_patch')]
    valid_patches = [p for p in patches if '---' in p.get('fix_patch', '') and '+++' in p.get('fix_patch', '')]
    score = min(1.0, len(valid_patches) / max(len(review), 1))
    detail = f'{len(valid_patches)}/{len(review)} defects have valid unified diff patches'
    print(json.dumps({'score': round(score, 2), 'passed': len(valid_patches) >= 1, 'detail': detail}))
"
