#!/usr/bin/env bash
# check_drift_points.sh — verify agent identified drift points
# Reimplemented in bash+jq+grep (no python3 in container). Scoring semantics
# are identical to the previous python implementation: for each ground-truth
# drift point, its lowercased 'key' must appear as a substring of the lowercased
# JSON dump of the agent's drift_points; score = round(found/total, 2), passes
# at >= 0.5.
set -euo pipefail

export REPORT="${WORKSPACE}/agent_output/answer.json"
export GT_FILE="${TASK_DIR}/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 0
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 0
fi

# Lowercased JSON dump of the agent's drift_points (default to []).
agent_text=$(jq -c '.drift_points // []' "$REPORT" | tr '[:upper:]' '[:lower:]')

gt_total=$(jq '.drift_points // [] | length' "$GT_FILE")

found=0
for ((i = 0; i < gt_total; i++)); do
    key=$(jq -r ".drift_points[$i].key // \"\"" "$GT_FILE" | tr '[:upper:]' '[:lower:]')
    if [[ -n "$key" ]] && printf '%s' "$agent_text" | grep -qF -- "$key"; then
        found=$((found + 1))
    fi
done

# total = max(len(gt_points), 1)
if [[ "$gt_total" -ge 1 ]]; then total="$gt_total"; else total=1; fi

# score = round(found/total, 2), rendered with python float repr (e.g. 0.0, 0.5, 1.0).
score=$(awk "BEGIN {printf \"%.2f\", $found/$total}")
score=${score%0}; score=${score%.}; case "$score" in *.*) ;; *) score="$score.0";; esac
# passed = (rounded score) >= 0.5
if awk "BEGIN {exit !($score >= 0.5)}"; then passed=true; else passed=false; fi

printf '{"score": %s, "passed": %s, "detail": "Found %d/%d drift points"}\n' \
    "$score" "$passed" "$found" "$total"
