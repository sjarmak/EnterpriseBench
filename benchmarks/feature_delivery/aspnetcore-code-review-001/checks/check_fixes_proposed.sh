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
import json, os, re

# Ground-truth anchors: patches must reference one of these paths
GT_PATH_PREFIX = 'src/Components/'
GT_BASENAMES = {
    'DisplayName.cs',
    'ExpressionMemberAccessor.cs',
    'InputBase.cs',
}

def patch_has_real_path(patch_text):
    '''
    Return True if the --- header line references a real ground-truth path.
    Rejects /dev/null, fabricated roots, or missing path information.
    '''
    for line in patch_text.splitlines():
        if line.startswith('--- '):
            path = line[4:].split('\t')[0].strip()
            # Reject null or empty source
            if path in ('/dev/null', '', 'a/'):
                return False
            path_lower = path.lower().lstrip('ab/')
            basename = path_lower.split('/')[-1]
            if path_lower.startswith(GT_PATH_PREFIX.lower()):
                return True
            if basename in {n.lower() for n in GT_BASENAMES}:
                return True
            return False
    return False

review = json.load(open(os.environ['REVIEW_FILE']))
if not isinstance(review, list):
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'review.json is not a JSON array'}))
else:
    patches = [d for d in review if d.get('fix_patch')]

    # A patch is structurally valid if it has both --- and +++ markers
    structurally_valid = [
        p for p in patches
        if '---' in p.get('fix_patch', '') and '+++' in p.get('fix_patch', '')
    ]

    # A patch is semantically valid if it also references a real ground-truth path
    semantically_valid = [
        p for p in structurally_valid
        if patch_has_real_path(p.get('fix_patch', ''))
    ]

    total = max(len(review), 1)
    # Score: 30% weight for structural validity + 70% weight for semantic validity
    struct_score = min(1.0, len(structurally_valid) / total)
    sem_score = min(1.0, len(semantically_valid) / total)
    score = round(0.3 * struct_score + 0.7 * sem_score, 2)

    passed = len(semantically_valid) >= 1
    detail = (
        f'{len(structurally_valid)}/{len(review)} patches have valid diff markers; '
        f'{len(semantically_valid)}/{len(review)} reference a ground-truth path '
        f'(src/Components/ or known filename)'
    )
    print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
