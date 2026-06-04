#!/usr/bin/env bash
# check_compliance.sh — verify agent identifies contract compliance issues
# Implemented in bash+jq+grep (no python3 in container). Scoring identical to the
# previous python3 implementation: deduped set of contract_chain words (lowercased,
# >4 chars, alphabetic) matched as substrings in json.dumps(answer).lower(), plus a
# fixed compliance-term list. score=min(1,matched/max(len*0.4,1)); comp=min(1,m/3).
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

answer_text=$(jq -r '
  def pyd:
    if type=="object" then "{" + ([to_entries[] | (.key|tojson) + ": " + (.value|pyd)] | join(", ")) + "}"
    elif type=="array" then "[" + ([.[]|pyd] | join(", ")) + "]"
    else tojson end;
  pyd' "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')

# Deduped set of chain terms: lowercase, alphabetic (str.isalpha, ASCII), len>4.
mapfile -t gt_terms < <(jq -r '(.contract_chain // [])[]' "$GT_FILE" \
  | tr '[:upper:]' '[:lower:]' | tr -s '[:space:]' '\n' \
  | grep -E '^[a-z]+$' | awk '{ if (length($0)>4) print }' | sort -u)
n_terms=${#gt_terms[@]}

matched=0
for term in "${gt_terms[@]}"; do
  if printf '%s' "$answer_text" | grep -qF -- "$term"; then matched=$((matched + 1)); fi
done

comp_matched=0
for c in serializ json contract drift mismatch breaking compat; do
  if printf '%s' "$answer_text" | grep -qF -- "$c"; then comp_matched=$((comp_matched + 1)); fi
done
n_comp=7

# python round(x,2) as json.dumps(float): round-half-even (glibc awk) + float repr.
round2() {
  awk -v x="$1" 'BEGIN{ s=sprintf("%.2f", x); sub(/0+$/, "", s); if (s ~ /\.$/) s=s"0"; print s }'
}
raw=$(jq -n --argjson m "$matched" --argjson n "$n_terms" --argjson c "$comp_matched" \
  '([1.0, $m/([$n*0.4, 1]|max)]|min) as $score
   | ([1.0, $c/3.0]|min) as $comp
   | ($score*0.6 + $comp*0.4)')
final_score=$(round2 "$raw")
passed=$(jq -rn --argjson s "$final_score" 'if $s>=0.3 then "true" else "false" end')

printf '{"score": %s, "passed": %s, "detail": "Chain concepts: %s/%s, compliance terms: %s/%s"}\n' \
  "$final_score" "$passed" "$matched" "$n_terms" "$comp_matched" "$n_comp"
