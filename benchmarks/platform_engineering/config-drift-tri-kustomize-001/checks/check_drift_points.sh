#!/usr/bin/env bash
# check_drift_points.sh — verify agent identified drift points across all three tools
# Reimplemented in bash+jq+grep (no python3 in container). Weighted scoring
# (repos 0.6 + concepts 0.4, round to 2dp) and pass logic are identical to the
# previous python implementation. NOTE: the original python rendered the repo
# list in 'detail' via list(set(...)), whose order is NON-DETERMINISTIC across
# runs (PYTHONHASHSEED is unset). 'score' and 'passed' are deterministic and
# matched exactly; the repo list here is emitted in detection order
# (kustomize, argocd, flux), a stable representative of the python output.
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/DRIFT_REPORT.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

points_text=$(jq -c '.drift_points // []' "$REPORT" | tr '[:upper:]' '[:lower:]')
has() { printf '%s' "$points_text" | grep -qF -- "$1"; }

repos=()
has kustomize && repos+=("kustomize")
has argo && repos+=("argocd")
has flux && repos+=("flux")
num_repos=${#repos[@]}

# python list repr: ['a', 'b']
repos_repr="["
for ((j = 0; j < num_repos; j++)); do
  [[ $j -gt 0 ]] && repos_repr+=", "
  repos_repr+="'${repos[$j]}'"
done
repos_repr+="]"

matched=0
for c in "strategic merge" list normaliz patch reconcil tracking; do
  if has "$c"; then matched=$((matched + 1)); fi
done

raw=$(awk "BEGIN {rs=$num_repos/3.0; cs=$matched/3.0; if(cs>1.0)cs=1.0; printf \"%.10f\", rs*0.6+cs*0.4}")
score=$(awk "BEGIN {printf \"%.2f\", $raw}")
score=${score%0}; score=${score%.}; case "$score" in *.*) ;; *) score="$score.0";; esac

if [[ "$num_repos" -ge 2 && "$matched" -ge 2 ]]; then passed=true; else passed=false; fi

printf '{"score": %s, "passed": %s, "detail": "Repos covered: %s, concepts matched: %d/6"}\n' \
  "$score" "$passed" "$repos_repr" "$matched"
