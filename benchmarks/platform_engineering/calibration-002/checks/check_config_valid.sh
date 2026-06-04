#!/usr/bin/env bash
# check_config_valid.sh — validate corrected config if provided
# Uses bash + jq + grep (no python3 in container). Scoring semantics identical to
# the previous python implementation: has_chain = truthy(override_chain else drift_points);
# has_fix = truthy(fix else corrected_config); score 1.0/0.6/0.5/0.2 accordingly.
set -euo pipefail

export REPORT="${WORKSPACE}/agent_output/answer.json"

if [[ ! -f "$REPORT" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 0
fi

# Mirror python: answer.get('a', answer.get('b', default)) — present key wins even if
# falsy; bool() truthiness: empty list/dict/string/0/null/false -> false.
has_chain=$(jq -r '
  (if has("override_chain") then .override_chain else (.drift_points // []) end)
  | (. != null and . != false and . != 0 and . != "" and . != [] and . != {})
' "$REPORT")
has_fix=$(jq -r '
  (if has("fix") then .fix else (.corrected_config // "") end)
  | (. != null and . != false and . != 0 and . != "" and . != [] and . != {})
' "$REPORT")

if [[ "$has_chain" == "true" && "$has_fix" == "true" ]]; then
    echo '{"score": 1.0, "passed": true, "detail": "Override chain and fix provided"}'
elif [[ "$has_chain" == "true" ]]; then
    echo '{"score": 0.6, "passed": true, "detail": "Override chain provided, no fix"}'
elif [[ "$has_fix" == "true" ]]; then
    echo '{"score": 0.5, "passed": true, "detail": "Fix provided, no override chain"}'
else
    echo '{"score": 0.2, "passed": false, "detail": "No override chain or fix provided"}'
fi
