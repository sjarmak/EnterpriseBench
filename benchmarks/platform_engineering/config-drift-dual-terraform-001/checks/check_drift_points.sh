#!/usr/bin/env bash
# check_drift_points.sh — verify agent identified drift points between Terraform core and AWS provider
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/DRIFT_REPORT.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

python3 -c "
import json, os

report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])

# Check that drift points reference both repos
has_core = any('terraform_core' in json.dumps(p).lower() or 'eval_diff' in json.dumps(p).lower() or 'eval_refresh' in json.dumps(p).lower() for p in points)
has_provider = any('provider' in json.dumps(p).lower() or 'aws' in json.dumps(p).lower() for p in points)

# Check for key drift concepts
concepts = ['json', 'normaliz', 'policy', 'security_group', 'phantom', 'set', 'list', 'ordering', 'default']
matched = sum(1 for c in concepts if any(c in json.dumps(p).lower() for p in points))

repos_score = (1.0 if has_core else 0.0) * 0.5 + (1.0 if has_provider else 0.0) * 0.5
concept_score = min(1.0, matched / 3.0)
score = round(repos_score * 0.6 + concept_score * 0.4, 2)
passed = has_core and has_provider and matched >= 2

detail = f'Core referenced: {has_core}, provider referenced: {has_provider}, concepts matched: {matched}/{len(concepts)}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
