#!/usr/bin/env bash
# check_drift_points.sh — verify agent identified drift points across all three tools
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

# Check that drift points reference all three repos
repos_mentioned = set()
for p in points:
    text = json.dumps(p).lower()
    if 'kustomize' in text:
        repos_mentioned.add('kustomize')
    if 'argo' in text:
        repos_mentioned.add('argocd')
    if 'flux' in text:
        repos_mentioned.add('flux')

# Check for key drift concepts
concepts = ['strategic merge', 'list', 'normaliz', 'patch', 'reconcil', 'tracking']
matched_concepts = sum(1 for c in concepts if any(c in json.dumps(p).lower() for p in points))

repos_score = len(repos_mentioned) / 3.0
concept_score = min(1.0, matched_concepts / 3.0)
score = round(repos_score * 0.6 + concept_score * 0.4, 2)
passed = len(repos_mentioned) >= 2 and matched_concepts >= 2

detail = f'Repos covered: {list(repos_mentioned)}, concepts matched: {matched_concepts}/{len(concepts)}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
