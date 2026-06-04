#!/usr/bin/env bash
# check_test_impact.sh — verify agent identifies test impact of schema changes
# bash+jq+grep (no python3 in container). Scoring semantics identical to the
# previous python implementation.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

# Original python did json.load(open(...)) with no try/except: invalid JSON
# aborts with a traceback (non-zero exit, no stdout). Mirror it.
if ! jq -e . "$ANSWER_FILE" >/dev/null 2>&1; then
  exit 1
fi

# answer_text = json.dumps(answer).lower()
answer_text=$(jq -c . "$ANSWER_FILE" | tr '[:upper:]' '[:lower:]')

has() { printf '%s' "$answer_text" | grep -qF -- "$1"; }

# matched = count of test_concepts present as substrings
matched=0
for c in 'test' 'spec' 'fixture' 'migration_test' 'schema_test' 'integration'; do
  if has "$c"; then matched=$((matched + 1)); fi
done

# repos_with_tests: one point per group if any term in the group is present
repos_with_tests=0
for grp in 'supabase migration' 'postgrest haskell schemacache' 'gotrue token session'; do
  for r in $grp; do
    if has "$r"; then repos_with_tests=$((repos_with_tests + 1)); break; fi
  done
done

# score = round(min(1.0, matched/3)*0.5 + min(1.0, repos/2)*0.5, 2) banker's rounding
score=$(jq -n --argjson m "$matched" --argjson r "$repos_with_tests" '
  (([1.0, ($m / 3.0)] | min) * 0.5 + ([1.0, ($r / 2.0)] | min) * 0.5) as $s |
  ($s * 100) as $v | ($v | floor) as $fl | ($v - $fl) as $fr |
  ((if $fr < 0.5 then $fl elif $fr > 0.5 then $fl + 1
    else (if ($fl % 2) == 0 then $fl else $fl + 1 end) end) / 100) | tostring' | tr -d '"')
case "$score" in *.*) ;; *) score="${score}.0";; esac

# passed = matched >= 1 and repos_with_tests >= 2
if [[ "$matched" -ge 1 && "$repos_with_tests" -ge 2 ]]; then passed=true; else passed=false; fi

printf '{"score": %s, "passed": %s, "detail": "Test concepts: %s/6, repos with test awareness: %s/3"}\n' \
  "$score" "$passed" "$matched" "$repos_with_tests"
