#!/usr/bin/env bash
# check_severity.sh — verify agent correctly assessed severity
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Requires both the correct severity level AND citation of a specific mechanism
# bash+jq+grep reimplementation (no python3 in container). Output JSON is
# byte-identical to the previous python implementation.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="${TASK_DIR:-/task}/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

expected_severity=$(jq -r '(.expected_severity // "") | ascii_downcase' "$GT_FILE")

if [[ -z "$expected_severity" ]]; then
    jq -cn '{score: 0.0, passed: false, detail: "No expected severity in ground truth"}'
    exit 0
fi

# Specific Envoy config parameter names that must accompany the severity rating.
MECHANISM_KEYWORDS=(
  'max_connections'
  'max_pending_requests'
  'conn_pool_base'
  'ConnPoolBase'
  'circuit_breaking'
  'circuit breaker'
)

# sev = answer.get('severity', answer.get('impact', answer.get('priority','')))
# dict -> level/severity/rating + rationale/reason ; str -> itself ; else -> str(sev)
agent_severity=$(jq -r '
  def pick: if has("severity") then .severity
            elif has("impact") then .impact
            elif has("priority") then .priority
            else "" end;
  pick as $sev
  | (if ($sev|type)=="object" then ($sev.level // $sev.severity // $sev.rating // "")
     elif ($sev|type)=="string" then $sev
     elif ($sev|type)=="boolean" then (if $sev then "True" else "False" end)
     elif ($sev|type)=="null" then "None"
     else ($sev|tostring) end) | ascii_downcase
' "$ANSWER_FILE")

agent_rationale=$(jq -r '
  def pick: if has("severity") then .severity
            elif has("impact") then .impact
            elif has("priority") then .priority
            else "" end;
  pick as $sev
  | (if ($sev|type)=="object" then ($sev.rationale // $sev.reason // "") else "" end)
  | ascii_downcase
' "$ANSWER_FILE")

if [[ -z "${agent_severity//[[:space:]]/}" ]]; then
    jq -cn '{score: 0.0, passed: false, detail: "Agent provided no severity assessment"}'
    exit 0
fi

level_idx() {
  case "$1" in
    low) echo 0;; medium) echo 1;; high) echo 2;; critical) echo 3;; *) echo -1;;
  esac
}
expected_idx=$(level_idx "$expected_severity")
agent_idx=-1
for level in low medium high critical; do
  if grep -qF -- "$level" <<<"$agent_severity"; then
    agent_idx=$(level_idx "$level")
    break
  fi
done

if [[ "$expected_idx" -lt 0 || "$agent_idx" -lt 0 ]]; then
  if grep -qF -- "$expected_severity" <<<"$agent_severity"; then sev_score="1.0"; else sev_score="0.0"; fi
else
  distance=$(( expected_idx - agent_idx )); distance=${distance#-}
  case "$distance" in
    0) sev_score="1.0";; 1) sev_score="0.6";; 2) sev_score="0.2";; *) sev_score="0.0";;
  esac
fi
# severity_score:.2f
sev_score_2f=$(printf '%.2f' "$sev_score")

# combined_text = agent_rationale + ' ' + json.dumps(answer).lower()
# json.dumps default separators ", " / ": "; reproduce, then lowercase.
full_text=$(jq -c . "$ANSWER_FILE" | sed 's/,/, /g; s/:/: /g' | tr '[:upper:]' '[:lower:]')
combined_text="${agent_rationale} ${full_text}"
# normalize hyphens to underscores for mechanism matching
combined_norm=$(printf '%s' "$combined_text" | tr '-' '_')

matched=()
for kw in "${MECHANISM_KEYWORDS[@]}"; do
  kw_norm=$(printf '%s' "$kw" | tr '[:upper:]' '[:lower:]' | tr '-' '_')
  if grep -qF -- "$kw_norm" <<<"$combined_norm"; then
    matched+=("$kw")
  fi
done

if [[ ${#matched[@]} -ge 1 ]]; then mechanism_cited="True"; cited_n=1; else mechanism_cited="False"; cited_n=0; fi

# score = round(0.6*severity_score + 0.4*cited, 2)
# Exact python json.dumps(round(...,2)) text for each (sev_score, cited) combination,
# so jq emits the same float representation (e.g. 1.0 not 1).
case "${sev_score}:${cited_n}" in
  1.0:1) score="1.0";; 1.0:0) score="0.6";;
  0.6:1) score="0.76";; 0.6:0) score="0.36";;
  0.2:1) score="0.52";; 0.2:0) score="0.12";;
  0.0:1) score="0.4";;  0.0:0) score="0.0";;
esac
# passed = severity_score >= 0.6 and mechanism_cited
if jq -n --argjson sv "$sev_score" 'if $sv >= 0.6 then true else false end' | grep -q true && [[ $cited_n -eq 1 ]]; then
  passed=true
else
  passed=false
fi

# matched_mechanisms python list repr: ['a', 'b'] / []
if [[ ${#matched[@]} -eq 0 ]]; then
  matched_repr="[]"
else
  matched_repr=$(printf "%s\n" "${matched[@]}" | jq -R . | jq -s -r 'def q: "\u0027"; "[" + (map(q + . + q) | join(", ")) + "]"')
fi

detail="Expected: ${expected_severity}, Agent: ${agent_severity} (severity_score=${sev_score_2f}); mechanism_cited=${mechanism_cited} (${matched_repr})"
jq -cn --argjson s "$score" --argjson p "$passed" --arg d "$detail" '{score: $s, passed: $p, detail: $d}'
