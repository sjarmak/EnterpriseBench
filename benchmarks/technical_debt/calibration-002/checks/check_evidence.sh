#!/usr/bin/env bash
# check_evidence.sh — validate reasoning quality for dead code claims
set -euo pipefail

REPORT="${WORKSPACE}/agent_output/answer.json"

if [[ ! -f "$REPORT" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 0
fi

# bash+jq+grep (no python3 in container). Semantics identical to the prior python3:
# items = answer.dead_code (key-present-wins) else dead_exports else []; if falsy →
# "No dead code items found"; else count dict items with truthy .evidence, score =
# round(with_evidence/len(items), 2), passed at >= 0.5.
items_falsy=$(jq -r '
  (if has("dead_code") then .dead_code elif has("dead_exports") then .dead_exports else [] end)
  | if (.==null or .==false or .==0 or .=="" or .==[] or .=={}) then "yes" else "no" end' "$REPORT")

if [[ "$items_falsy" == "yes" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No dead code items found"}'
    exit 0
fi

# total = len(items); with_evidence = dict items whose .evidence is truthy
# (non-empty string / nonzero number / true / non-empty array|object).
read -r with_ev total < <(jq -r '
  (if has("dead_code") then .dead_code elif has("dead_exports") then .dead_exports else [] end) as $it
  | [ $it
      | (if type=="array" then .[] elif type=="object" then keys[] else empty end)
      | select(type=="object")
      | .evidence
      | select(. != null and . != false and . != 0 and . != "" and . != [] and . != {}) ] | length
    as $w
  | "\($w) \($it|length)"' "$REPORT")

pyfloat() { printf '%.*f' "$2" "$1" | sed -e 's/0*$//' -e 's/\.$/.0/'; }
score=$(awk -v w="$with_ev" -v t="$total" 'BEGIN{printf "%.10f", w/t}')
score_r=$(pyfloat "$score" 2)
passed=$(awk -v s="$score" 'BEGIN{print (s>=0.5)?"true":"false"}')
printf '{"score": %s, "passed": %s, "detail": "%s/%s items have evidence"}\n' "$score_r" "$passed" "$with_ev" "$total"
