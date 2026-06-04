#!/usr/bin/env bash
# check_indirect_refs.sh — verify agent traces indirect schema dependencies
# bash+jq+grep (no python3 in container). Scoring semantics identical to the
# previous python implementation.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

# The original python loaded GT and answer with no try/except; a missing or
# unparseable file aborts with a traceback (non-zero exit, no stdout). Mirror it.
if [[ ! -f "$GT_FILE" ]] || ! jq -e . "$GT_FILE" >/dev/null 2>&1 || ! jq -e . "$ANSWER_FILE" >/dev/null 2>&1; then
  exit 1
fi

# answer_text = json.dumps(answer).lower()
answer_text=$(jq -c . "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')

# gt_terms = set of lowercased words from impact_chain steps with len>4 and isalpha.
n_steps=$(jq -r '(.impact_chain // []) | length' "$GT_FILE")
set -f
terms=$(
  for ((i = 0; i < n_steps; i++)); do
    step=$(jq -r ".impact_chain[$i]" "$GT_FILE" | tr '[:upper:]' '[:lower:]')
    for w in $step; do
      if [[ ${#w} -gt 4 && "$w" =~ ^[a-z]+$ ]]; then
        printf '%s\n' "$w"
      fi
    done
  done | sort -u
)
set +f

if [[ -z "$terms" ]]; then
  n_terms=0
else
  n_terms=$(printf '%s\n' "$terms" | grep -c '')
fi

matched=0
if [[ "$n_terms" -gt 0 ]]; then
  while IFS= read -r term; do
    [[ -n "$term" ]] || continue
    if printf '%s' "$answer_text" | grep -qF -- "$term"; then
      matched=$((matched + 1))
    fi
  done <<< "$terms"
fi

# score = min(1.0, matched / max(len*0.4, 1)); round(.,2) with banker's rounding;
# passed = score >= 0.3.
score=$(jq -n --argjson m "$matched" --argjson n "$n_terms" '
  ([($n * 0.4), 1] | max) as $den |
  ([1.0, ($m / $den)] | min) as $s |
  ($s * 100) as $v | ($v | floor) as $fl | ($v - $fl) as $fr |
  ((if $fr < 0.5 then $fl elif $fr > 0.5 then $fl + 1
    else (if ($fl % 2) == 0 then $fl else $fl + 1 end) end) / 100) | tostring' | tr -d '"')
case "$score" in *.*) ;; *) score="${score}.0";; esac
passed=$(jq -n --argjson m "$matched" --argjson n "$n_terms" '
  ([($n * 0.4), 1] | max) as $den |
  if ([1.0, ($m / $den)] | min) >= 0.3 then true else false end')
printf '{"score": %s, "passed": %s, "detail": "Matched %s/%s impact chain concepts"}\n' \
  "$score" "$passed" "$matched" "$n_terms"
