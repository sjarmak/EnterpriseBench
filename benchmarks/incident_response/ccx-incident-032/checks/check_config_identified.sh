#!/usr/bin/env bash
# check_config_identified.sh — verify agent identified circuit breaker config
# bash+jq+grep (no python3 in container). Scoring semantics identical to the
# previous python implementation.
set -euo pipefail

ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
if [[ ! -f "$ANSWER_FILE" ]]; then
    ANSWER_FILE="${WORKSPACE:-/workspace}/answer.json"
fi
export ANSWER_FILE

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

# The original python did `json.load(open(...))` with no try/except: invalid
# JSON aborts with a traceback and a non-zero exit (no stdout). Mirror that.
if ! jq -e . "$ANSWER_FILE" >/dev/null 2>&1; then
    exit 1
fi

# text = json.dumps(answer).lower()
text=$(jq -c . "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')

found=0
for kw in 'circuit_breaker' 'circuit breaker' 'max_connections' 'max_pending_requests' 'thresholds'; do
    if printf '%s' "$text" | grep -qF -- "$kw"; then
        found=$((found + 1))
    fi
done

# score = min(1.0, found / 2.0); round(score, 2); passed = score >= 0.5
score=$(jq -n --argjson f "$found" '
  ([1.0, ($f / 2.0)] | min) as $s |
  ($s * 100) as $v | ($v | floor) as $fl | ($v - $fl) as $fr |
  ((if $fr < 0.5 then $fl elif $fr > 0.5 then $fl + 1
    else (if ($fl % 2) == 0 then $fl else $fl + 1 end) end) / 100) | tostring' | tr -d '"')
case "$score" in *.*) ;; *) score="${score}.0";; esac
passed=$(jq -n --argjson f "$found" 'if ([1.0, ($f / 2.0)] | min) >= 0.5 then true else false end')
printf '{"score": %s, "passed": %s, "detail": "Found %s/5 circuit breaker config keywords"}\n' \
    "$score" "$passed" "$found"
