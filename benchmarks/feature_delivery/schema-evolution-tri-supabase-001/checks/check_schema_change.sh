#!/usr/bin/env bash
# check_schema_change.sh — verify agent identifies the schema migration in Supabase
# bash+jq+grep (no python3 in container). Scoring semantics identical to the
# previous python implementation.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

# Original python loaded both files with no try/except; missing/unparseable
# aborts with a traceback (non-zero exit, no stdout). Mirror it.
if [[ ! -f "$GT_FILE" ]] || ! jq -e . "$GT_FILE" >/dev/null 2>&1 || ! jq -e . "$ANSWER_FILE" >/dev/null 2>&1; then
  exit 1
fi

# gt_files = [f.path for f in required_files if f.repo == 'supabase']
n_gt=$(jq -r '[ (.required_files // [])[] | select(.repo == "supabase") ] | length' "$GT_FILE")

# agent_files = answer.source_files // files // schema_files // []
# agent_text = ' '.join(str(f) for f in agent_files) when list else str(agent_files).
# Realistic answers carry a list of path strings; that is reproduced exactly here.
agent_type=$(jq -r '(.source_files // .files // .schema_files // []) | type' "$ANSWER_FILE")
if [[ "$agent_type" == "array" ]]; then
  agent_text=$(jq -r '(.source_files // .files // .schema_files // []) | map(tostring) | join(" ")' "$ANSWER_FILE")
else
  agent_text=$(jq -r '(.source_files // .files // .schema_files // []) | tostring' "$ANSWER_FILE")
fi

# found = count of gt files whose full path OR basename appears in agent_text
# (case-SENSITIVE literal substring, no lowercasing here).
found=0
for ((i = 0; i < n_gt; i++)); do
  gt_f=$(jq -r "[ (.required_files // [])[] | select(.repo == \"supabase\") ][$i].path" "$GT_FILE")
  base=${gt_f##*/}
  if printf '%s' "$agent_text" | grep -qF -- "$gt_f" || printf '%s' "$agent_text" | grep -qF -- "$base"; then
    found=$((found + 1))
  fi
done

# kw_match over json.dumps(answer).lower(); kw_score = min(1.0, kw_match/3.0)
answer_lc=$(jq -c . "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')
kw_match=0
for kw in 'auth.users' 'auth.sessions' 'rls' 'migration' 'schema'; do
  if printf '%s' "$answer_lc" | grep -qF -- "$kw"; then
    kw_match=$((kw_match + 1))
  fi
done

# final_score = round(score*0.6 + kw_score*0.4, 2) with banker's rounding;
# passed = final_score >= 0.4.
score=$(jq -n --argjson f "$found" --argjson n "$n_gt" --argjson k "$kw_match" '
  ($f / ([$n, 1] | max)) as $sc |
  ([1.0, ($k / 3.0)] | min) as $kw |
  ($sc * 0.6 + $kw * 0.4) as $fs |
  ($fs * 100) as $v | ($v | floor) as $fl | ($v - $fl) as $fr |
  ((if $fr < 0.5 then $fl elif $fr > 0.5 then $fl + 1
    else (if ($fl % 2) == 0 then $fl else $fl + 1 end) end) / 100) | tostring' | tr -d '"')
case "$score" in *.*) ;; *) score="${score}.0";; esac
passed=$(jq -n --argjson sc "$score" 'if $sc >= 0.4 then true else false end')
printf '{"score": %s, "passed": %s, "detail": "Found %s/%s schema files, %s/5 keywords"}\n' \
  "$score" "$passed" "$found" "$n_gt" "$kw_match"
