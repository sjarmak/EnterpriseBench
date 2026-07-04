#!/usr/bin/env bash
# check_origin_and_grammar.sh -- agent located the 'illegal header line' origin
# in h11's reader, the validate() helper, the grammar regex, and the
# whitespace-before-colon violation. Each group lists accepted phrasing
# variants; score = matched groups / total groups.

set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

python3 -c "
import json, os

answer_text = json.dumps(json.load(open(os.environ['ANSWER_FILE']))).lower()

groups = {
    'origin_file': ['_readers.py', 'h11._readers'],
    'origin_message': ['illegal header line'],
    'grammar_regex': ['header_field_re', '_abnf', 'field-name grammar', 'field_name regex'],
    'validate_helper': ['validate(', '_util.py', 'h11._util'],
    'whitespace_violation': [
        'before the colon', 'space in the header name', 'space in the field name',
        'whitespace in the field name', 'whitespace in the header name',
        'trailing space', 'space before', 'whitespace before',
    ],
}

matched = [name for name, alts in groups.items()
           if any(alt in answer_text for alt in alts)]
score = len(matched) / len(groups)
detail = f'Matched {len(matched)}/{len(groups)} origin/grammar groups: {sorted(matched)}'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.6, 'detail': detail}))
"
