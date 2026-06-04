#!/usr/bin/env bash
# check_error_source.sh — verify agent identified the correct source file + function
# bash+jq+grep reimplementation (no python3 in container). Scoring is identical to the
# previous inline-python: GT required paths vs agent file list
# (source_files // files // error_source.files; dict items -> path//file; str value kept),
# both newline-split with blank lines dropped; a GT path counts when it is a substring of
# or a suffix of any agent path; score = round(found/total, 2), passes at >= 0.5.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

if [[ ! -f "$GT_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No ground_truth.json found"}'
    exit 1
fi

# GT required file paths, one per line (matches python: for f in required_files: print(f['path']))
GT_FILES=$(jq -r '(.required_files // [])[] | .path' "$GT_FILE")

# Agent files, one per line. Fallback chain source_files / files / error_source.files
# (python dict.get key-presence semantics). list -> per item (dict path//file, else value);
# str -> printed as-is.
AGENT_FILES=$(jq -r '
  ( if has("source_files") then .source_files
    elif has("files") then .files
    elif (has("error_source") and (.error_source | type) == "object")
      then (if (.error_source | has("files")) then .error_source.files else [] end)
    else [] end ) as $files
  | if ($files | type) == "array" then
      $files[]
      | if type == "object" then (if has("path") then (.path // null) else (.file // "") end)
        else . end
      | if . == null then "" else tostring end
    elif ($files | type) == "string" then $files
    else empty end
' "$ANSWER_FILE")

# Newline-split, strip, drop blanks (python: [f.strip() for f in ... if f.strip()])
mapfile -t gt_files < <(printf '%s\n' "$GT_FILES" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$' || true)
mapfile -t agent_files < <(printf '%s\n' "$AGENT_FILES" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$' || true)

total=${#gt_files[@]}
if [[ "$total" -eq 0 ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No GT files"}'
    exit 0
fi

found=0
for gt in "${gt_files[@]}"; do
    hit=0
    for af in "${agent_files[@]}"; do
        if [[ "$af" == *"$gt"* ]] || [[ "$af" == *"$gt" ]]; then
            hit=1
            break
        fi
    done
    found=$((found + hit))
done

# score = round(found/total, 2) (IEEE ties-to-even, python repr) ; passes at >= 0.5.
read -r score passed < <(jq -nr --argjson f "$found" --argjson t "$total" '
    ($f / $t) as $x
    | ($x * 100) as $y
    | ($y | floor) as $fl
    | ($y - $fl) as $d
    | ( if $d < 0.5 then $fl
        elif $d > 0.5 then $fl + 1
        else (if ($fl % 2) == 0 then $fl else $fl + 1 end) end ) as $r2
    | ($r2 / 100) as $sc
    | "\($sc | tojson) \(if $sc >= 0.5 then "true" else "false" end)"')
[[ "$score" == *.* ]] || score="${score}.0"
printf '{"score": %s, "passed": %s, "detail": "Found %s/%s required source files"}\n' \
    "$score" "$passed" "$found" "$total"
