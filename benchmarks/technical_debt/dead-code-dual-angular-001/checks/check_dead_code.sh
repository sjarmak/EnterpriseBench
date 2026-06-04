#!/usr/bin/env bash
# check_dead_code.sh — verify agent identifies dead exported APIs
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

# bash+jq+grep (no python3 in container). Semantics identical to the prior python3:
# exports = answer.dead_exports//exports//symbols (key-present-wins); if not a non-empty
# list → "No dead exports identified". Else per dict item: +1 if it has symbol AND category,
# elif it has name OR export → +0.5. struct = min(1, valid/max(len,1)); pkg_covered = how
# many of @angular/{core,common,forms} appear in lower(json.dumps(exports)); pkg = covered/3;
# score = round(struct*0.6 + pkg*0.4, 2); passed = valid>=1 and pkg_covered>=1.

# python loads GT but never uses it; a missing GT still aborts the script (FileNotFoundError).
jq -e . "$GT_FILE" >/dev/null 2>&1 || exit 1

# exports value (key-present-wins). type=="array" check; emptiness handled below.
EXPORTS='(if has("dead_exports") then .dead_exports
          elif has("exports") then .exports
          elif has("symbols") then .symbols else [] end)'

is_nonempty_list=$(jq -r "$EXPORTS"' | if (type=="array" and length>0) then "yes" else "no" end' "$ANSWER_FILE")

if [[ "$is_nonempty_list" != "yes" ]]; then
    printf '{"score": 0.0, "passed": false, "detail": "No dead exports identified"}\n'
    exit 0
fi

# valid2 = 2*valid (integer): +2 if (symbol and category), +1 elif (name or export).
read -r valid2 nexp < <(jq -r "$EXPORTS"' as $e
  | ([ $e[]
      | if (type=="object" and has("symbol") and has("category")) then 2
        elif (type=="object" and (has("name") or has("export"))) then 1
        else 0 end ] | add // 0) as $v2
  | "\($v2) \($e|length)"' "$ANSWER_FILE")

# pkg_covered: literal substring search over lowercased compact JSON of exports.
exports_lc=$(jq -c "$EXPORTS" "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')
pkg_covered=0
for p in '@angular/core' '@angular/common' '@angular/forms'; do
    if printf '%s' "$exports_lc" | grep -qF -- "$p"; then
        pkg_covered=$((pkg_covered + 1))
    fi
done

# valid_int = int(valid) = floor(valid2/2) toward zero (valid2 >= 0 here).
valid_int=$((valid2 / 2))
score=$(awk -v v2="$valid2" -v n="$nexp" -v pc="$pkg_covered" 'BEGIN{
  valid = v2/2.0
  denom = (n>1)?n:1
  struct = valid/denom; if (struct>1.0) struct=1.0
  pkg = pc/3.0
  printf "%.10f", struct*0.6 + pkg*0.4
}')
pyfloat() { printf '%.*f' "$2" "$1" | sed -e 's/0*$//' -e 's/\.$/.0/'; }
score_r=$(pyfloat "$score" 2)
# passed = valid>=1 (i.e. valid2>=2) and pkg_covered>=1
if [[ "$valid2" -ge 2 && "$pkg_covered" -ge 1 ]]; then passed=true; else passed=false; fi
printf '{"score": %s, "passed": %s, "detail": "%s/%s well-structured exports, %s/3 packages covered"}\n' \
  "$score_r" "$passed" "$valid_int" "$nexp" "$pkg_covered"
