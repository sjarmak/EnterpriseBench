#!/usr/bin/env bash
# check_source_files.sh — verify agent identified the core routing hierarchy files
# Reimplemented in bash+jq+grep (no python3 in container — the task image ships
# bash/grep/jq but not python3, so the previous `python3 -c` body exited 127).
# Scoring semantics are identical to the python implementation: a required file
# counts as found when its GT path is a substring of, or a suffix of, any agent
# file entry, OR when its basename appears as a substring of json.dumps(answer).
# If answer.json is unparseable JSON or not a dict, the agent file list is empty
# and the raw file contents are searched for basenames (python try/except path).
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 0
fi

export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

mapfile -t gt_files < <(jq -r '.required_files // [] | .[] | .path' "$GT_FILE")
total=${#gt_files[@]}

# Parse answer.json. On parse failure OR non-dict answer, fall back to raw text
# with an empty agent file list (python `except Exception` branch).
agent_files=()
if answer_type=$(jq -r 'type' "$ANSWER_FILE" 2>/dev/null) && [[ "$answer_type" == "object" ]]; then
    mapfile -t agent_files < <(jq -r '
      (.files // [])
      | .[]
      | if type=="object" then (.path // "")
        elif type=="string" then .
        elif type=="boolean" then (if . then "True" else "False" end)
        elif type=="null" then "None"
        else tostring end' "$ANSWER_FILE")
    # json.dumps(answer) — python default separators ", " / ": " (with spaces).
    agent_text=$(jq -c . "$ANSWER_FILE" | sed 's/,/, /g; s/:/: /g')
else
    agent_text=$(cat "$ANSWER_FILE")
fi

found=0
for gt_f in "${gt_files[@]}"; do
    basename=${gt_f##*/}
    hit=0
    for af in "${agent_files[@]}"; do
        if [[ "$af" == *"$gt_f"* || "$af" == *"$gt_f" ]]; then
            hit=1
            break
        fi
    done
    if [[ $hit -eq 0 && "$agent_text" == *"$basename"* ]]; then
        hit=1
    fi
    [[ $hit -eq 1 ]] && found=$((found + 1))
done

if [[ "$total" -eq 0 ]]; then
    printf '{"score": 0, "passed": false, "detail": "Found %s/%s required hierarchy files"}\n' "$found" "$total"
    exit 0
fi

score=$(jq -n --argjson f "$found" --argjson t "$total" '
  (($f / $t * 100) | round) / 100
  | if . == (. | floor) then "\(.).0" else (. | tostring) end' | tr -d '"')
passed=$(jq -n --argjson f "$found" --argjson t "$total" 'if ($f / $t) >= 0.5 then true else false end')
printf '{"score": %s, "passed": %s, "detail": "Found %s/%s required hierarchy files"}\n' \
    "$score" "$passed" "$found" "$total"
