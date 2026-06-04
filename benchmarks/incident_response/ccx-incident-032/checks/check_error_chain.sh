#!/usr/bin/env bash
# check_error_chain.sh — verify agent traced the error propagation chain
# Reimplemented in bash+jq+grep (no python3 in container); scoring semantics identical to the prior python3 implementation.
set -euo pipefail

ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
if [[ ! -f "$ANSWER_FILE" ]]; then
    ANSWER_FILE="${WORKSPACE:-/workspace}/answer.json"
fi
export ANSWER_FILE
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

facts=$(jq -rn --slurpfile gt "$GT_FILE" --slurpfile ans "$ANSWER_FILE" '
  ($gt[0]) as $g | ($ans[0]) as $a |
  (if ($g|type)=="object" then ($g.error_chain) else null end) as $gtc0 |
  ($gtc0 // []) as $gtc |
  (($gtc0==null) or ($gtc0==false) or ($gtc0==0) or ($gtc0=="") or ($gtc0==[]) or ($gtc0=={})) as $gt_empty |
  if $gt_empty then "GTEMPTY"
  elif ($a|type)!="object" then "NONOBJ"
  else
    (if ($a|has("chain")) then $a.chain
     elif ($a|has("error_chain")) then $a.error_chain
     elif ($a|has("text")) then $a.text
     else "" end) as $ac |
    # python: " ".join(str(s) for s in ac) if isinstance(ac,list) else str(ac); then .lower()
    (if ($ac|type)=="array" then ([ $ac[] | tostring ] | join(" "))
     else ($ac|tostring) end | ascii_downcase) as $txt |
    ([ $gtc[] | tostring | ascii_downcase | splits("[ \t\n\r\f]+")
       | select(length>4) | select(test("^[a-z]+$")) ] | unique) as $kw |
    ([ $kw[] | select(. as $k | $txt | contains($k)) ] | length) as $m |
    "OK \($m) \($kw|length)"
  end')

case "$facts" in
  GTEMPTY) echo '{"score": 0.0, "passed": false, "detail": "No GT error chain defined"}'; exit 0 ;;
  NONOBJ)  exit 1 ;;
esac

read -r _ matched setlen <<<"$facts"

# score = min(matched/max(setlen*0.5,1),1.0); output round(score,2); pass at unrounded score>=0.3
if [[ $setlen -ge 2 ]]; then num=$((2*matched)); den=$setlen; else num=$matched; den=1; fi
if [[ $num -ge $den ]]; then h=100; else
  q=$((num*100/den)); r=$((num*100%den)); twice=$((2*r))
  if   [[ $twice -lt $den ]]; then h=$q
  elif [[ $twice -gt $den ]]; then h=$((q+1))
  else if [[ $((q%2)) -eq 0 ]]; then h=$q; else h=$((q+1)); fi
  fi
fi
intp=$((h/100)); frac=$((h%100))
if   [[ $frac -eq 0 ]]; then score=$(printf '%d.0' "$intp")
elif [[ $((frac%10)) -eq 0 ]]; then score=$(printf '%d.%d' "$intp" "$((frac/10))")
else score=$(printf '%d.%02d' "$intp" "$frac")
fi
if [[ $num -ge $den ]]; then passed=true
elif [[ $setlen -ge 2 ]]; then if [[ $((20*matched)) -ge $((3*setlen)) ]]; then passed=true; else passed=false; fi
else if [[ $((10*matched)) -ge 3 ]]; then passed=true; else passed=false; fi
fi

printf '{"score": %s, "passed": %s, "detail": "Matched %s/%s key concepts in error chain"}\n' "$score" "$passed" "$matched" "$setlen"
