#!/usr/bin/env bash
# check_cross_repo_usage.sh — verify agent traces usage across Angular and Components repos
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

python3 -c "
import json, os

answer = json.load(open(os.environ['ANSWER_FILE']))
gt = json.load(open(os.environ['GT_FILE']))

exports = answer.get('dead_exports', answer.get('exports', answer.get('symbols', [])))
answer_text = json.dumps(answer).lower()

# Check for cross-repo analysis evidence
has_angular_refs = 'public_api.ts' in answer_text or 'angular/angular' in answer_text
has_components_refs = 'components' in answer_text or 'material' in answer_text or 'cdk' in answer_text

# Check categories used
categories = set()
for e in (exports if isinstance(exports, list) else []):
    if isinstance(e, dict):
        cat = e.get('category', '')
        if cat:
            categories.add(cat)

expected_cats = {'truly_dead', 'components_only', 'test_only'}
cat_coverage = len(categories & expected_cats) / len(expected_cats)

repo_score = (1.0 if has_angular_refs else 0.0) * 0.5 + (1.0 if has_components_refs else 0.0) * 0.5
score = round(repo_score * 0.6 + cat_coverage * 0.4, 2)
passed = has_angular_refs and has_components_refs and len(categories) >= 1

detail = f'Angular refs: {has_angular_refs}, Components refs: {has_components_refs}, categories: {categories}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
