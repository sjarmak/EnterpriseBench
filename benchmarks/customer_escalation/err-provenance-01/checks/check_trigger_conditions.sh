#!/usr/bin/env bash
# check_trigger_conditions.sh — verify agent identified trigger conditions
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Checks keyword/concept match against ground truth trigger_conditions
# bash+jq+grep (no python3 in container). Scoring identical to prior python:
# per GT condition, keywords = lowercased words >3 chars; condition counts as
# matched if ANY keyword is a literal substring of the lowercased space-joined
# agent conditions; score = matched/len, round 2, passes at >= 0.3.
set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

gt_total=$(jq '(.trigger_conditions // []) | length' "$GT_FILE")
if [[ "$gt_total" -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No GT trigger conditions defined"}'
    exit 0
fi

agent_count=$(jq '((.trigger_conditions // .conditions // .triggers) // []) | length' "$ANSWER_FILE")
if [[ "$agent_count" -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "Agent did not identify trigger conditions"}'
    exit 0
fi

# agent_text = ' '.join(str(c) for c in agent_conditions).lower()
agent_text=$(jq -r '((.trigger_conditions // .conditions // .triggers) // []) | map(
  if type=="object" then tojson elif type=="array" then tojson else tostring end
) | join(" ")' "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')

matched=0
for ((i = 0; i < gt_total; i++)); do
    cond=$(jq -r ".trigger_conditions[$i]" "$GT_FILE")
    cond_lc=$(printf '%s' "$cond" | tr '[:upper:]' '[:lower:]')
    hit=0
    # keywords = words >3 chars (whitespace split); ANY substring match => matched
    set -f
    for word in $cond_lc; do
        if [[ ${#word} -gt 3 ]]; then
            if printf '%s' "$agent_text" | grep -qF -- "$word"; then
                hit=1
                break
            fi
        fi
    done
    set +f
    [[ $hit -eq 1 ]] && matched=$((matched + 1))
done

read -r score passed < <(jq -n --argjson m "$matched" --argjson t "$gt_total" '
  (($m / $t * 100 | round) / 100) as $s
  | (if ($s | floor) == $s then "\($s).0" else "\($s)" end) as $sf
  | "\($sf) \(if $s >= 0.3 then "true" else "false" end)"' | tr -d '"')

printf '{"score": %s, "passed": %s, "detail": "Matched %s/%s trigger conditions"}\n' \
  "$score" "$passed" "$matched" "$gt_total"
