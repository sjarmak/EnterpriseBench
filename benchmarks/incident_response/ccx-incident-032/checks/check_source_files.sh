#!/usr/bin/env bash
# check_source_files.sh — verify agent identified the correct source files
# Reimplemented in bash+jq+grep (no python3 in container — the task image ships
# bash/grep/jq but not python3, so the previous `python3 -c` body exited 127).
# Scoring semantics are identical to the python implementation: a required file
# counts as found when its GT path is a substring of, or a suffix of, any agent
# file entry. (No basename/text matching in this variant.)
set -euo pipefail

ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
if [[ ! -f "$ANSWER_FILE" ]]; then
    ANSWER_FILE="${WORKSPACE:-/workspace}/answer.json"
fi
export ANSWER_FILE
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found at '"$ANSWER_FILE"'"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

# A non-object answer makes python `answer.get(...)` raise AttributeError and the
# original script exits non-zero with no score line — preserve that.
if [[ "$(jq -r 'type' "$ANSWER_FILE" 2>/dev/null)" != "object" ]]; then
    echo "answer.json is not a JSON object" >&2
    exit 1
fi

mapfile -t gt_files < <(jq -r '.required_files // [] | .[] | .path' "$GT_FILE")
total=${#gt_files[@]}

mapfile -t agent_files < <(jq -r '
  (.files // [])
  | .[]
  | if type=="object" then (.path // "")
    elif type=="string" then .
    elif type=="boolean" then (if . then "True" else "False" end)
    elif type=="null" then "None"
    else tostring end' "$ANSWER_FILE")

if [[ "$total" -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No GT files"}'
    exit 0
fi

found=0
for gt_f in "${gt_files[@]}"; do
    for af in "${agent_files[@]}"; do
        if [[ "$af" == *"$gt_f"* || "$af" == *"$gt_f" ]]; then
            found=$((found + 1))
            break
        fi
    done
done

score=$(jq -n --argjson f "$found" --argjson t "$total" '
  (($f / $t * 100) | round) / 100
  | if . == (. | floor) then "\(.).0" else (. | tostring) end' | tr -d '"')
passed=$(jq -n --argjson f "$found" --argjson t "$total" 'if ($f / $t) >= 0.5 then true else false end')
printf '{"score": %s, "passed": %s, "detail": "Found %s/%s required source files"}\n' \
    "$score" "$passed" "$found" "$total"
