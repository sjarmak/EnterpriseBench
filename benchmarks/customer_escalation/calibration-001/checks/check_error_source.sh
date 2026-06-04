#!/usr/bin/env bash
# check_error_source.sh — verify agent identified the correct source file + function
# bash+jq+grep reimplementation (no python3 in container). Scoring semantics are
# identical to the previous inline-python: agent file list from
# source_files // files // error_source.files (dict items unwrapped via path//file),
# a GT path counts as found when it is a substring of, or a suffix of, any agent
# path; score = round(found/total, 2), passes at >= 0.5.
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

# GT required paths, one per line (NUL-safe not needed: paths have no newlines).
mapfile -t gt_paths < <(jq -r '(.required_files // [])[] | .path' "$GT_FILE")
total=${#gt_paths[@]}

# Agent files: first present of source_files / files / error_source.files; must be a
# list, else empty. dict item -> .get('path', .get('file','')) (key-present-but-empty
# is kept as empty); str item -> itself.
mapfile -t agent_files < <(jq -r '
  ( if has("source_files") then .source_files
    elif has("files") then .files
    elif (has("error_source") and (.error_source | type) == "object")
      then (if (.error_source | has("files")) then .error_source.files else [] end)
    else [] end ) as $raw
  | if ($raw | type) == "array" then
      $raw[]
      | if type == "object" then (if has("path") then (.path // null) else (.file // "") end)
        elif type == "string" then .
        else empty end
      | if . == null then "" else tostring end
    else empty end
' "$ANSWER_FILE")

if [[ "$total" -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No required files in GT"}'
    exit 0
fi

if [[ ${#agent_files[@]} -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "Agent provided no files"}'
    exit 0
fi

found=0
for gt in "${gt_paths[@]}"; do
    hit=0
    for af in "${agent_files[@]}"; do
        # substring match OR endswith
        if [[ "$af" == *"$gt"* ]] || [[ "$af" == *"$gt" ]]; then
            hit=1
            break
        fi
    done
    found=$((found + hit))
done

# score = round(found/total, 2) using IEEE doubles with ties-to-even (python round),
# emitted in python float repr (jq tojson on a number == python repr for these values:
# integers keep ".0"). passed at >= 0.5.
read -r score passed < <(jq -nr --argjson f "$found" --argjson t "$total" '
    ($f / $t) as $x
    | ($x * 100) as $y
    | ($y | floor) as $fl
    | ($y - $fl) as $d
    | ( if $d < 0.5 then $fl
        elif $d > 0.5 then $fl + 1
        else (if ($fl % 2) == 0 then $fl else $fl + 1 end) end ) as $r2   # ties to even
    | ($r2 / 100) as $sc
    | "\($sc | tojson) \(if $sc >= 0.5 then "true" else "false" end)"')
# python float repr always shows a decimal point; jq prints integral doubles as "1".
[[ "$score" == *.* ]] || score="${score}.0"
printf '{"score": %s, "passed": %s, "detail": "Found %s/%s required source files"}\n' \
    "$score" "$passed" "$found" "$total"
