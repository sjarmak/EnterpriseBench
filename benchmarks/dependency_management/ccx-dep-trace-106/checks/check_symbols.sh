#!/usr/bin/env bash
# check_symbols.sh — verify agent identified key structs/functions
# Implemented in bash+jq+grep (no python3 in container). Scoring identical to the
# previous python3 implementation: for each expected symbol, match if the symbol
# (or its underscore-stripped form against the underscore-stripped answer text)
# appears in json.dumps(answer).lower(); score = found/len(expected) (round 2dp).
set -euo pipefail

ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
if [[ ! -f "$ANSWER_FILE" ]]; then
    ANSWER_FILE="${WORKSPACE:-/workspace}/answer.json"
fi
export ANSWER_FILE

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

text=$(jq -r '
  def pyd:
    if type=="object" then "{" + ([to_entries[] | (.key|tojson) + ": " + (.value|pyd)] | join(", ")) + "}"
    elif type=="array" then "[" + ([.[]|pyd] | join(", ")) + "]"
    else tojson end;
  pyd' "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')
text_nounder=$(printf '%s' "$text" | tr -d '_')

expected=(opt_pass pass_manager execute_pass_list tree_ssa_dce passes.def)
found=0
for sym in "${expected[@]}"; do
  sym_nounder=$(printf '%s' "$sym" | tr -d '_')
  if printf '%s' "$text_nounder" | grep -qF -- "$sym_nounder" \
     || printf '%s' "$text" | grep -qF -- "$sym"; then
    found=$((found + 1))
  fi
done
n=5

round2() {
  awk -v x="$1" 'BEGIN{ s=sprintf("%.2f", x); sub(/0+$/, "", s); if (s ~ /\.$/) s=s"0"; print s }'
}
raw=$(jq -n --argjson f "$found" --argjson n "$n" '$f/$n')
score=$(round2 "$raw")
passed=$(jq -rn --argjson f "$found" --argjson n "$n" 'if ($f/$n)>=0.4 then "true" else "false" end')

printf '{"score": %s, "passed": %s, "detail": "Identified %s/%s expected pass registration symbols"}\n' \
  "$score" "$passed" "$found" "$n"
