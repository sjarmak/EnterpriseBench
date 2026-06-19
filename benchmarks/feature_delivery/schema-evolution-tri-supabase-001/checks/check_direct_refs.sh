#!/usr/bin/env bash
# check_direct_refs.sh — verify agent finds direct references in PostgREST and GoTrue
# Implemented in bash+jq+grep (no python3 in container). Scoring identical to the
# previous python3 implementation: count PostgREST and GoTrue GT file paths (full
# path or basename, lowercased) appearing in json.dumps(answer).lower();
# score = total_found/max(total_expected,1) (round 2dp); passes when both repos hit.
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

# Count GT paths for a repo matched by full path or basename; sets COUNT and N_FILES.
COUNT=0
N_FILES=0
count_repo() {  # $1 = repo name
  local repo="$1" f fl basel
  local files
  COUNT=0
  mapfile -t files < <(jq -r --arg r "$repo" '((.required_files // []) + (.sufficient_files // []))[] | select(.repo==$r) | .path' "$GT_FILE")
  N_FILES=${#files[@]}
  for f in "${files[@]}"; do
    fl=$(printf '%s' "$f" | tr '[:upper:]' '[:lower:]')
    basel=$(printf '%s' "${f##*/}" | tr '[:upper:]' '[:lower:]')
    if printf '%s' "$answer_text" | grep -qF -- "$fl" || printf '%s' "$answer_text" | grep -qF -- "$basel"; then
      COUNT=$((COUNT + 1))
    fi
  done
}

count_repo postgrest; postgrest_found=$COUNT; n_postgrest=$N_FILES
count_repo gotrue;    gotrue_found=$COUNT;    n_gotrue=$N_FILES

total_expected=$((n_postgrest + n_gotrue))
total_found=$((postgrest_found + gotrue_found))

denom=$total_expected; [[ "$denom" -lt 1 ]] && denom=1
round2() {
  awk -v x="$1" 'BEGIN{ s=sprintf("%.2f", x); sub(/0+$/, "", s); if (s ~ /\.$/) s=s"0"; print s }'
}
raw=$(jq -n --argjson f "$total_found" --argjson d "$denom" '$f/$d')
score=$(round2 "$raw")

if [[ "$postgrest_found" -ge 1 && "$gotrue_found" -ge 1 ]]; then
  passed=true
else
  passed=false
fi

printf '{"score": %s, "passed": %s, "detail": "PostgREST: %s/%s, GoTrue: %s/%s"}\n' \
  "$score" "$passed" "$postgrest_found" "$n_postgrest" "$gotrue_found" "$n_gotrue"
