#!/usr/bin/env bash
# check_cross_repo_usage.sh — verify agent traces usage across Angular and Components repos
# bash+jq+grep (no python3 in container). Scoring semantics (score + passed) are
# identical to the previous python implementation.
#
# DETAIL CAVEAT: the python f-string embedded `categories: {set}` — a raw Python
# set repr whose element ORDER is randomized per process (PYTHONHASHSEED), so the
# original's detail string is itself non-deterministic across runs. We reproduce a
# deterministic Python-style set repr (first-seen insertion order). score/passed
# are byte-identical; the category ordering inside detail may differ from any one
# python run (the python output is not stable either). See GROUP report.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

# Original python loaded both files with no try/except; a missing or unparseable
# file aborts with a traceback (non-zero exit, no stdout). Mirror it.
if [[ ! -f "$GT_FILE" ]] || ! jq -e . "$ANSWER_FILE" >/dev/null 2>&1 || ! jq -e . "$GT_FILE" >/dev/null 2>&1; then
  exit 1
fi

# answer_text = json.dumps(answer).lower()
answer_text=$(jq -c . "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')
has() { printf '%s' "$answer_text" | grep -qF -- "$1"; }

# has_angular_refs / has_components_refs (literal lowercased substrings)
if has 'public_api.ts' || has 'angular/angular'; then has_angular=1; else has_angular=0; fi
if has 'components' || has 'material' || has 'cdk'; then has_components=1; else has_components=0; fi

# exports = answer.dead_exports // exports // symbols // []
# categories = set of non-empty .category over dict entries of a list-typed exports.
exports_type=$(jq -r '(.dead_exports // .exports // .symbols // []) | type' "$ANSWER_FILE")
cats_ordered=()
if [[ "$exports_type" == "array" ]]; then
  while IFS= read -r cat; do
    [[ -n "$cat" ]] || continue
    dup=0
    for c in "${cats_ordered[@]:-}"; do [[ "$c" == "$cat" ]] && dup=1 && break; done
    [[ "$dup" -eq 0 ]] && cats_ordered+=("$cat")
  done < <(jq -r '
    (.dead_exports // .exports // .symbols // [])
    | map(select(type=="object"))
    | map(.category // "")
    | map(select(. != ""))
    | .[]' "$ANSWER_FILE")
fi
n_cats=${#cats_ordered[@]}

# cat_coverage = |categories ∩ {truly_dead, components_only, test_only}| / 3
inter=0
for c in "${cats_ordered[@]:-}"; do
  case "$c" in truly_dead|components_only|test_only) inter=$((inter + 1));; esac
done

# repo_score = has_angular*0.5 + has_components*0.5
# score = round(repo_score*0.6 + cat_coverage*0.4, 2) with banker's rounding
score=$(jq -n --argjson a "$has_angular" --argjson cp "$has_components" --argjson i "$inter" '
  (($a * 0.5 + $cp * 0.5) * 0.6 + ($i / 3.0) * 0.4) as $s |
  ($s * 100) as $v | ($v | floor) as $fl | ($v - $fl) as $fr |
  ((if $fr < 0.5 then $fl elif $fr > 0.5 then $fl + 1
    else (if ($fl % 2) == 0 then $fl else $fl + 1 end) end) / 100) | tostring' | tr -d '"')
case "$score" in *.*) ;; *) score="${score}.0";; esac

# passed = has_angular and has_components and len(categories) >= 1
if [[ "$has_angular" -eq 1 && "$has_components" -eq 1 && "$n_cats" -ge 1 ]]; then passed=true; else passed=false; fi

# bool reprs (python True/False) for detail
[[ "$has_angular" -eq 1 ]] && a_repr=True || a_repr=False
[[ "$has_components" -eq 1 ]] && c_repr=True || c_repr=False

# Python-style set repr: set() when empty, else {'a', 'b', ...}
if [[ "$n_cats" -eq 0 ]]; then
  set_repr="set()"
else
  set_repr="{"
  for ((j = 0; j < n_cats; j++)); do
    [[ "$j" -gt 0 ]] && set_repr+=", "
    set_repr+="'${cats_ordered[$j]}'"
  done
  set_repr+="}"
fi

printf '{"score": %s, "passed": %s, "detail": "Angular refs: %s, Components refs: %s, categories: %s"}\n' \
  "$score" "$passed" "$a_repr" "$c_repr" "$set_repr"
