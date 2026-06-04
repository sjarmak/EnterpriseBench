#!/usr/bin/env bash
# check_severity.sh — verify agent assessed severity correctly
# bash+jq+grep reimplementation (no python3 in container). Output JSON is
# byte-identical to the previous python implementation.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE}/agent_output/answer.json"
export GT_FILE="${TASK_DIR}/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

# expected = str(gt.get('expected_severity','medium')).lower()
expected=$(jq -r '(.expected_severity // "medium") | ascii_downcase' "$GT_FILE")

# actual = str(answer.get('severity', answer.get('impact',''))).lower()
# Reproduce python str() of the chosen value (key-present semantics), then lowercase.
actual=$(jq -r '
  def q: "\u0027";
  def pyrepr_inner:
    if type=="string" then q + . + q
    elif type=="object" then "{" + ([to_entries[] | q + .key + q + ": " + (.value|pyrepr_inner)] | join(", ")) + "}"
    elif type=="array" then "[" + ([.[]|pyrepr_inner] | join(", ")) + "]"
    elif type=="boolean" then (if . then "True" else "False" end)
    elif type=="null" then "None"
    else tostring end;
  def pyrepr:
    if type=="string" then .
    elif type=="object" then "{" + ([to_entries[] | q + .key + q + ": " + (.value|pyrepr_inner)] | join(", ")) + "}"
    elif type=="array" then "[" + ([.[]|pyrepr_inner] | join(", ")) + "]"
    elif type=="boolean" then (if . then "True" else "False" end)
    elif type=="null" then "None"
    else tostring end;
  (if has("severity") then .severity elif has("impact") then .impact else "" end) | pyrepr | ascii_downcase
' "$ANSWER_FILE")

if grep -qF -- "$expected" <<<"$actual"; then
    jq -cn --arg e "$expected" '{score: 1.0, passed: true, detail: ("Severity matches: " + $e)}'
elif [[ -n "$actual" ]]; then
    jq -cn --arg e "$expected" --arg a "$actual" '{score: 0.3, passed: false, detail: ("Expected " + $e + ", got " + $a)}'
else
    jq -cn '{score: 0.0, passed: false, detail: "No severity assessment provided"}'
fi
