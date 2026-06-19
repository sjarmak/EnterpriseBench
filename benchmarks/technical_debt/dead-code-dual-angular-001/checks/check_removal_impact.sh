#!/usr/bin/env bash
# check_removal_impact.sh — verify agent documents removal impact on Components packages
# Reimplemented in bash+jq (no python3 in container — the task image ships
# bash/grep/jq but not python3, so the previous `python3 -c` body exited 127).
# Scoring is identical: scan the dead_exports/exports/symbols list; an entry
# grants has_impact when its removal_impact is truthy with str-length > 5, and
# grants has_components_usage when its components_usage is a non-empty list.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

# A non-object answer makes python `answer.get(...)` raise AttributeError and the
# original script exits non-zero with no score line — preserve that.
if [[ "$(jq -r 'type' "$ANSWER_FILE" 2>/dev/null)" != "object" ]]; then
    echo "answer.json is not a JSON object" >&2
    exit 1
fi

# exports = answer.get('dead_exports', answer.get('exports', answer.get('symbols', [])))
# python .get returns the value when the key is present even if it is null; mirror
# that precedence: first present key wins.
has_impact=false
has_components_usage=false
while IFS= read -r line; do
    case "$line" in
        impact) has_impact=true ;;
        usage)  has_components_usage=true ;;
    esac
done < <(jq -r '
  (if has("dead_exports") then .dead_exports
   elif has("exports") then .exports
   elif has("symbols") then .symbols
   else [] end) as $exports
  | (if ($exports|type)=="array" then $exports else [] end)[]
  | select(type=="object")
  | ( if ((.removal_impact // null) as $ri
          | ($ri != null and $ri != false and $ri != "" and $ri != 0
             and $ri != [] and $ri != {})
            and (($ri|tostring) | length) > 5)
      then "impact" else empty end ),
    ( if ((.components_usage // null) | type) == "array"
         and ((.components_usage) | length) > 0
      then "usage" else empty end )' "$ANSWER_FILE")

# score = (0.5 if has_impact) + (0.5 if has_components_usage)
if $has_impact && $has_components_usage; then
    score="1.0"
elif $has_impact || $has_components_usage; then
    score="0.5"
else
    score="0.0"
fi
if $has_impact || $has_components_usage; then passed=true; else passed=false; fi

# python bool repr is capitalized (True/False) in the f-string detail.
pi=$($has_impact && echo True || echo False)
pu=$($has_components_usage && echo True || echo False)
printf '{"score": %s, "passed": %s, "detail": "Impact documented: %s, components usage traced: %s"}\n' \
    "$score" "$passed" "$pi" "$pu"
