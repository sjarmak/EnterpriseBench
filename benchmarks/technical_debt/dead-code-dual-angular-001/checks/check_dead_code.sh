#!/usr/bin/env bash
# check_dead_code.sh — verify agent identifies dead exported APIs
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

if not isinstance(exports, list) or len(exports) == 0:
    print(json.dumps({'score': 0.0, 'passed': False, 'detail': 'No dead exports identified'}))
else:
    # Check structure quality
    valid = 0
    for e in exports:
        if isinstance(e, dict) and 'symbol' in e and 'category' in e:
            valid += 1
        elif isinstance(e, dict) and ('name' in e or 'export' in e):
            valid += 0.5

    # Check that angular packages are covered
    answer_text = json.dumps(exports).lower()
    packages = ['@angular/core', '@angular/common', '@angular/forms']
    pkg_covered = sum(1 for p in packages if p in answer_text)

    struct_score = min(1.0, valid / max(len(exports), 1))
    pkg_score = pkg_covered / len(packages)
    score = round(struct_score * 0.6 + pkg_score * 0.4, 2)
    passed = valid >= 1 and pkg_covered >= 1

    detail = f'{int(valid)}/{len(exports)} well-structured exports, {pkg_covered}/{len(packages)} packages covered'
    print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
