#!/usr/bin/env bash
# check_removal_impact.sh — verify agent documents removal impact on Components packages
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

python3 -c "
import json, os

answer = json.load(open(os.environ['ANSWER_FILE']))
exports = answer.get('dead_exports', answer.get('exports', answer.get('symbols', [])))

has_impact = False
has_components_usage = False
for e in (exports if isinstance(exports, list) else []):
    if isinstance(e, dict):
        if e.get('removal_impact') and len(str(e['removal_impact'])) > 5:
            has_impact = True
        usage = e.get('components_usage', [])
        if isinstance(usage, list) and len(usage) > 0:
            has_components_usage = True

score = round((0.5 if has_impact else 0.0) + (0.5 if has_components_usage else 0.0), 2)
passed = has_impact or has_components_usage

detail = f'Impact documented: {has_impact}, components usage traced: {has_components_usage}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
