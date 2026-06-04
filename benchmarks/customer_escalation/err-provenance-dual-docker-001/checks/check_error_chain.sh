#!/usr/bin/env bash
# check_error_chain.sh — verify agent traced the error propagation chain
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Validates ordered call-path against ground truth error_chain
# Reimplemented in bash+jq+grep (no python3 in container); scoring semantics identical to the prior python3 implementation.
set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"
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
    (if ($a|has("error_chain")) then $a.error_chain
     elif ($a|has("propagation_chain")) then $a.propagation_chain
     elif ($a|has("chain")) then $a.chain
     else [] end) as $ac |
    (($ac==null) or ($ac==false) or ($ac==0) or ($ac=="") or ($ac==[]) or ($ac=={})) as $ac_empty |
    if $ac_empty then "ACEMPTY"
    else
      # GT terms: lowercased words, len>4 AND isalpha (ascii letters), set-deduped
      ([ $gtc[] | tostring | ascii_downcase | splits("[ \t\n\r\f]+")
         | select(length>4) | select(test("^[a-z]+$")) ] | unique) as $kw |
      # python: " ".join(str(s) for s in agent_chain).lower(); string iterates as chars
      ([ (if ($ac|type)=="string" then ($ac|explode|map([.]|implode)[])
          elif ($ac|type)=="array" then $ac[]
          else $ac end) | tostring ] | join(" ") | ascii_downcase) as $txt |
      ([ $kw[] | select(. as $k | $txt | contains($k)) ] | length) as $m |
      "OK \($m) \($kw|length)"
    end
  end')

case "$facts" in
  GTEMPTY) echo '{"score": 0.0, "passed": false, "detail": "No GT error chain defined"}'; exit 0 ;;
  ACEMPTY) echo '{"score": 0.0, "passed": false, "detail": "Agent did not provide error chain"}'; exit 0 ;;
  NONOBJ)  exit 1 ;;
esac

read -r _ matched setlen <<<"$facts"

# score = min(matched/max(setlen*0.5,1),1.0); pass at unrounded score>=0.3; output round(score,2)
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
# passed: UNROUNDED min(...) >= 0.3  (setlen>=2: 20*matched>=3*setlen ; else 10*matched>=3 ; capped at 1.0>=0.3 always true when num>=den)
if [[ $num -ge $den ]]; then passed=true
elif [[ $setlen -ge 2 ]]; then if [[ $((20*matched)) -ge $((3*setlen)) ]]; then passed=true; else passed=false; fi
else if [[ $((10*matched)) -ge 3 ]]; then passed=true; else passed=false; fi
fi

printf '{"score": %s, "passed": %s, "detail": "Matched %s/%s key concepts in error chain"}\n' "$score" "$passed" "$matched" "$setlen"
