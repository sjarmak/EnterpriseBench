#!/usr/bin/env bash
# check_defects_detected.sh — verify agent detected defects in the reviewed files
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

REVIEW_FILE="$WORKSPACE/review.json"
if [[ ! -f "$REVIEW_FILE" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "No review.json found"}\n'
    exit 0
fi

python3 -c "
import json
review = json.load(open('$REVIEW_FILE'))
if not isinstance(review, list):
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'review.json is not a JSON array'}))
else:
    count = len(review)
    # Expect at least 2 defects
    score = min(1.0, count / 3.0)
    has_required_fields = all(
        all(k in d for k in ('file', 'severity', 'description'))
        for d in review
    )
    if not has_required_fields:
        score *= 0.5
    detail = f'Detected {count} defects (required fields: {has_required_fields})'
    print(json.dumps({'score': round(score, 2), 'passed': count >= 2, 'detail': detail}))
"
