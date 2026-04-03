#!/usr/bin/env bash
# check_expected_values.sh — verify agent documents correct root cause for phantom diffs
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/DRIFT_REPORT.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

python3 -c "
import json, os

report = json.load(open(os.environ['REPORT']))
points = report.get('drift_points', [])

# Check that agent provides file paths from both repos
has_core_file = any('terraform_core_file' in p and p['terraform_core_file'] for p in points)
has_provider_file = any('provider_file' in p and p['provider_file'] for p in points)
has_impact = any('impact' in p and len(str(p['impact'])) > 10 for p in points)

file_score = (1.0 if has_core_file else 0.0) * 0.5 + (1.0 if has_provider_file else 0.0) * 0.5
score = round(file_score * 0.7 + (0.3 if has_impact else 0.0), 2)
passed = has_core_file and has_provider_file and has_impact

detail = f'Core file: {has_core_file}, provider file: {has_provider_file}, impact: {has_impact}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
