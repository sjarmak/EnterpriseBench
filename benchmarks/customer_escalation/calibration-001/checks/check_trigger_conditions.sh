#!/usr/bin/env bash
# check_trigger_conditions.sh — verify agent identified trigger conditions
# bash+jq+grep (no python3 in container). Scoring identical to prior python:
# gt_keywords = dedup set of lowercased words >3 chars across all GT conditions;
# agent_text = lowercased space-join of agent conditions; matched = gt_keywords
# appearing as literal substrings; score = round(min(matched/max(0.5*|kw|,1),1),2),
# passes at >= 0.4.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE}/agent_output/answer.json"
export GT_FILE="${TASK_DIR}/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

gt_count=$(jq '(.trigger_conditions // []) | length' "$GT_FILE")
if [[ "$gt_count" -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No trigger conditions in GT"}'
    exit 0
fi

# agent_conditions = answer.trigger_conditions // answer.conditions // []
agent_count=$(jq '((.trigger_conditions // .conditions) // []) | length' "$ANSWER_FILE")
if [[ "$agent_count" -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "Agent provided no trigger conditions"}'
    exit 0
fi

# agent_text: ' '.join(str(c) for c in agent_conditions).lower()
agent_text=$(jq -r '((.trigger_conditions // .conditions) // []) | map(
  if type=="object" then tojson elif type=="array" then tojson else tostring end
) | join(" ")' "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')

# gt_keywords: set of lowercased words >3 chars across all GT conditions
mapfile -t gt_kws < <(jq -r '.trigger_conditions[]' "$GT_FILE" \
  | tr '[:upper:]' '[:lower:]' | tr -s '[:space:]' '\n' \
  | awk '{ if (length($0) > 3) print }' | sort -u)

kw_total=${#gt_kws[@]}
matched=0
for kw in "${gt_kws[@]}"; do
    if printf '%s' "$agent_text" | grep -qF -- "$kw"; then
        matched=$((matched + 1))
    fi
done

read -r score passed < <(jq -n --argjson m "$matched" --argjson k "$kw_total" '
  ([($k * 0.5), 1] | max) as $denom
  | ([($m / $denom), 1.0] | min) as $raw
  | (($raw * 100 | round) / 100) as $s
  | (if ($s | floor) == $s then "\($s).0" else "\($s)" end) as $sf
  | "\($sf) \(if $s >= 0.4 then "true" else "false" end)"' | tr -d '"')

printf '{"score": %s, "passed": %s, "detail": "Matched %s keywords from trigger conditions"}\n' \
  "$score" "$passed" "$matched"
