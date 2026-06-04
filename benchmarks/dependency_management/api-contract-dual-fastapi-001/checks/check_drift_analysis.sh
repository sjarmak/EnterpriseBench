#!/usr/bin/env bash
# check_drift_analysis.sh — verify agent identifies contract drift between FastAPI and httpx
# Implemented in bash+jq+grep (no python3 in container). Scoring identical to the
# previous python3 implementation: count fixed drift concepts found in
# json.dumps(answer).lower(), plus FastAPI/httpx repo mentions.
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

has_term() { printf '%s' "$answer_text" | grep -qF -- "$1"; }

matched=0
for c in none missing optional default nested union serializ pydantic 422 content-type; do
  if has_term "$c"; then matched=$((matched + 1)); fi
done
n_concepts=10

has_fastapi=False; has_term fastapi && has_fastapi=True
has_httpx=False;   has_term httpx   && has_httpx=True

fa=0; [[ "$has_fastapi" == True ]] && fa=1
hx=0; [[ "$has_httpx" == True ]] && hx=1

# python round(x,2) as json.dumps(float): round-half-even (glibc awk) + float repr.
round2() {
  awk -v x="$1" 'BEGIN{ s=sprintf("%.2f", x); sub(/0+$/, "", s); if (s ~ /\.$/) s=s"0"; print s }'
}
raw=$(jq -n --argjson m "$matched" --argjson fa "$fa" --argjson hx "$hx" \
  '([1.0, $m/4.0]|min)*0.6 + ($fa*0.5 + $hx*0.5)*0.4')
score=$(round2 "$raw")

if [[ "$matched" -ge 3 && "$has_fastapi" == True && "$has_httpx" == True ]]; then
  passed=true
else
  passed=false
fi

printf '{"score": %s, "passed": %s, "detail": "Drift concepts: %s/%s, FastAPI: %s, httpx: %s"}\n' \
  "$score" "$passed" "$matched" "$n_concepts" "$has_fastapi" "$has_httpx"
