#!/usr/bin/env bash
# check_defects_detected.sh — verify agent detected defects in the reviewed files
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

export REVIEW_FILE="$WORKSPACE/agent_output/answer.json"
if [[ ! -f "$REVIEW_FILE" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
    exit 0
fi

python3 -c "
import json, os

# Ground-truth required files (basenames and partial paths accepted)
GT_FILES = [
    'DisplayName.cs',
    'ExpressionMemberAccessor.cs',
    'InputBase.cs',
    'src/Components/Web/src/Forms/DisplayName.cs',
    'src/Components/Web/src/Forms/ExpressionMemberAccessor.cs',
    'src/Components/Web/src/Forms/InputBase.cs',
]

review = json.load(open(os.environ['REVIEW_FILE']))
if not isinstance(review, list):
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'review.json is not a JSON array'}))
else:
    count = len(review)
    has_required_fields = all(
        all(k in d for k in ('file', 'severity', 'description'))
        for d in review
    )

    # Check how many defect entries reference a ground-truth file
    gt_basenames = {f.split('/')[-1].lower() for f in GT_FILES}
    gt_paths_lower = {f.lower() for f in GT_FILES}

    def references_gt_file(defect):
        file_val = str(defect.get('file', '')).lower()
        basename = file_val.split('/')[-1]
        return basename in gt_basenames or file_val in gt_paths_lower

    gt_matches = [d for d in review if references_gt_file(d)]
    gt_match_count = len(gt_matches)
    # Number of distinct GT files referenced (cap at 3 — the 3 expected files)
    distinct_gt_files = len({str(d.get('file', '')).lower().split('/')[-1] for d in gt_matches})

    # Base score: count of defects (need at least 2, full score at 3+)
    count_score = min(1.0, count / 3.0)

    # Retrieval score: proportion of ground-truth files referenced (out of 3 expected)
    retrieval_score = min(1.0, distinct_gt_files / 3.0)

    # Combined score: 40% count, 60% retrieval quality
    score = 0.4 * count_score + 0.6 * retrieval_score

    if not has_required_fields:
        score *= 0.5

    score = round(score, 2)
    passed = count >= 2 and gt_match_count >= 1
    detail = (
        f'Detected {count} defects; {gt_match_count} reference a ground-truth file '
        f'({distinct_gt_files} distinct GT files); required_fields={has_required_fields}'
    )
    print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
