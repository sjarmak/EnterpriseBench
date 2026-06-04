#!/usr/bin/env bash
# check_code_paths.sh — verify agent identified correct code paths
# Reads agent output from $WORKSPACE/agent_output/answer.json
# Compares against ground truth required_files + sufficient_files
# bash+jq+grep reimplementation (no python3 in container). Output JSON is
# byte-identical to the previous python implementation.
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

# required = gt.get('ground_truth', gt).get('required_files', [])
# sufficient = ... same shape
n_req=$(jq '((.ground_truth.required_files) // .required_files // []) | length' "$GT_FILE")
n_suf=$(jq '((.ground_truth.sufficient_files) // .sufficient_files // []) | length' "$GT_FILE")

# agent_files: from code_paths/files/source_files; dict->path/file, str->itself
n_agent=$(jq '
  (.code_paths // .files // .source_files // []) as $raw
  | (if ($raw|type)=="array" then $raw else [] end)
  | map(if type=="object" then (.path // .file // "") elif type=="string" then . else empty end)
  | length
' "$ANSWER_FILE")

if [[ "$n_req" -eq 0 ]]; then
    jq -cn '{score: 0.0, passed: false, detail: "No required files in ground truth"}'
    exit 0
fi

if [[ "$n_agent" -eq 0 ]]; then
    jq -cn '{score: 0.0, passed: false, detail: "Agent provided no code paths"}'
    exit 0
fi

# req_found / suf_found via shared path_match logic:
#   gt.strip('/')==ag.strip('/') OR ag.endswith(gt) OR gt.endswith(ag)
counts=$(jq -rn \
  --slurpfile gt "$GT_FILE" \
  --slurpfile ans "$ANSWER_FILE" '
  def strip_slash: sub("^/+";"") | sub("/+$";"");
  def pmatch($gt;$ag): ($gt|strip_slash)==($ag|strip_slash) or ($ag|endswith($gt)) or ($gt|endswith($ag));
  ($gt[0]) as $g | ($ans[0]) as $a
  | (($g.ground_truth.required_files) // $g.required_files // []) as $required
  | (($g.ground_truth.sufficient_files) // $g.sufficient_files // []) as $sufficient
  | (($a.code_paths // $a.files // $a.source_files // []) as $raw
     | (if ($raw|type)=="array" then $raw else [] end)
     | map(if type=="object" then (.path // .file // "") elif type=="string" then . else empty end)) as $agent
  | ([ $required[] | .path as $gp | (any($agent[]; pmatch($gp; .))) ] | map(select(.)) | length) as $reqf
  | ([ $sufficient[] | .path as $gp | (any($agent[]; pmatch($gp; .))) ] | map(select(.)) | length) as $suff
  | "\($reqf) \($suff)"
')
req_found=${counts% *}
suf_found=${counts#* }

# req_score = req_found/n_req ; suf_score = suf_found/max(n_suf,1)
# score = round(0.70*req_score + 0.30*suf_score, 2)
# Use the raw float from jq, then printf '%.2f' (glibc round-half-to-even on the
# exact double — matches python round(x,2)); finally normalize to python
# json.dumps text form (drop a single trailing zero: 0.70 -> 0.7, 1.00 -> 1.0).
raw=$(jq -n --argjson rf "$req_found" --argjson rt "$n_req" --argjson sf "$suf_found" --argjson st "$n_suf" '
  ($rf/$rt) as $rs | ($sf/([$st,1]|max)) as $ss | (0.70*$rs + 0.30*$ss)')
score=$(printf '%.2f' "$raw" | sed 's/\(\.[0-9]\)0$/\1/')

passed=$(jq -n --argjson s "$score" 'if $s >= 0.3 then true else false end')
detail="Found ${req_found}/${n_req} required, ${suf_found}/${n_suf} sufficient files"
jq -cn --argjson s "$score" --argjson p "$passed" --arg d "$detail" '{score: $s, passed: $p, detail: $d}'
