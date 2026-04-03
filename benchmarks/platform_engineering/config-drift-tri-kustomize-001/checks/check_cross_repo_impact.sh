#!/usr/bin/env bash
# check_cross_repo_impact.sh — verify agent documented cross-repo impact
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
gt = json.load(open(os.environ['GT_FILE']))

points = report.get('drift_points', [])

# Check that agent provides source file paths from multiple repos
has_kustomize_file = any('kustomize_source_file' in p and p['kustomize_source_file'] for p in points)
has_argocd_file = any('argocd_source_file' in p and p['argocd_source_file'] for p in points)
has_flux_file = any('flux_source_file' in p and p['flux_source_file'] for p in points)
has_impact = any('impact' in p and len(str(p['impact'])) > 10 for p in points)

file_repos = sum([has_kustomize_file, has_argocd_file, has_flux_file])
score = round((file_repos / 3.0) * 0.7 + (0.3 if has_impact else 0.0), 2)
passed = file_repos >= 2 and has_impact

detail = f'Source files from {file_repos}/3 repos, impact documented: {has_impact}'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
