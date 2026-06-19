#!/usr/bin/env bash
# check_expected_values.sh — verify agent determined correct expected values
# Reimplemented in bash+jq+grep (no python3 in container). Scoring semantics are
# identical to the previous python implementation: each ground-truth drift
# point's lowercased 'expected' string must appear as a substring of the
# lowercased JSON dump of the agent's drift_points; score = round(matched/total,
# 2), passes at >= 0.5.
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

gt_total=$(jq '.drift_points // [] | length' "$GT_FILE")
agent_total=$(jq '.drift_points // [] | length' "$REPORT")

if [[ "$gt_total" -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No GT drift points"}'
    exit 0
fi
if [[ "$agent_total" -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "Agent provided no drift points"}'
    exit 0
fi

# Lowercased compact JSON dump of the agent's drift_points list. The 'expected'
# search phrases live inside single string values, so structural separator
# spacing (python ", "/": " vs jq ",":") never affects the substring match;
# compact output preserves in-string content verbatim, which is what matters.
agent_text=$(jq -c '.drift_points' "$REPORT" | tr '[:upper:]' '[:lower:]')

matched=0
for ((i = 0; i < gt_total; i++)); do
    # str(gp.get('expected','')): jq tostring mirrors python str() for scalars.
    expected=$(jq -r '.drift_points['"$i"'].expected | if . == null then "" else (.|tostring) end' "$GT_FILE" \
        | tr '[:upper:]' '[:lower:]')
    if [[ -n "$expected" ]] && printf '%s' "$agent_text" | grep -qF -- "$expected"; then
        matched=$((matched + 1))
    fi
done

score=$(awk "BEGIN {printf \"%.2f\", $matched/$gt_total}")
score=${score%0}; score=${score%.}; case "$score" in *.*) ;; *) score="$score.0";; esac
if awk "BEGIN {exit !($score >= 0.5)}"; then passed=true; else passed=false; fi

printf '{"score": %s, "passed": %s, "detail": "Matched %d/%d expected values"}\n' \
    "$score" "$passed" "$matched" "$gt_total"
