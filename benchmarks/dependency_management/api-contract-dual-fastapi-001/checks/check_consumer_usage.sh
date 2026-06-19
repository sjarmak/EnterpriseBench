#!/usr/bin/env bash
# check_consumer_usage.sh — verify agent finds httpx request encoding logic
# Implemented in bash+jq+grep (no python3 in container). Scoring semantics are
# identical to the previous python3 implementation: count httpx GT file paths
# (full path or basename, lowercased) that appear in json.dumps(answer).lower(),
# plus a fixed keyword set; score = file_score*0.6 + kw_score*0.4 (round 2dp).
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

# python json.dumps(answer).lower(): reproduce ", "/": " separators, then lowercase.
answer_text=$(jq -r '
  def pyd:
    if type=="object" then "{" + ([to_entries[] | (.key|tojson) + ": " + (.value|pyd)] | join(", ")) + "}"
    elif type=="array" then "[" + ([.[]|pyd] | join(", ")) + "]"
    else tojson end;
  pyd' "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')

# httpx-repo GT paths from required_files + sufficient_files (order preserved)
mapfile -t gt_files < <(jq -r '((.required_files // []) + (.sufficient_files // []))[] | select(.repo=="httpx") | .path' "$GT_FILE")

found=0
for f in "${gt_files[@]}"; do
  fl=$(printf '%s' "$f" | tr '[:upper:]' '[:lower:]')
  basel=$(printf '%s' "${f##*/}" | tr '[:upper:]' '[:lower:]')
  if printf '%s' "$answer_text" | grep -qF -- "$fl" || printf '%s' "$answer_text" | grep -qF -- "$basel"; then
    found=$((found + 1))
  fi
done
n_gt=${#gt_files[@]}

kw_found=0
for kw in httpx _content _models encoding json serializ request; do
  if printf '%s' "$answer_text" | grep -qF -- "$kw"; then
    kw_found=$((kw_found + 1))
  fi
done
n_kw=7

denom=$n_gt; [[ "$denom" -lt 1 ]] && denom=1
# python round(x,2) as json.dumps(float): round-half-even (glibc awk) + float repr.
round2() {
  awk -v x="$1" 'BEGIN{ s=sprintf("%.2f", x); sub(/0+$/, "", s); if (s ~ /\.$/) s=s"0"; print s }'
}
raw=$(jq -n --argjson f "$found" --argjson d "$denom" --argjson k "$kw_found" \
  '($f/$d)*0.6 + ([1.0, $k/3.0]|min)*0.4')
score=$(round2 "$raw")
passed=$(jq -n --argjson f "$found" --argjson k "$kw_found" 'if ($f>=1 or $k>=3) then true else false end')
printf '{"score": %s, "passed": %s, "detail": "httpx files: %s/%s, keywords: %s/%s"}\n' \
  "$score" "$passed" "$found" "$n_gt" "$kw_found" "$n_kw"
