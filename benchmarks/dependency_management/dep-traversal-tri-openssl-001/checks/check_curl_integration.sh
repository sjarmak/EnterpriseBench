#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced curl's OpenSSL backend configuration path
# Implemented in bash+jq+grep (no python3 in container). Scoring identical to the
# previous python3 implementation: for each integration_path step, its words longer
# than 4 chars (lowercased) are keywords; the step matches when >= 30% of those
# keywords appear as literal substrings in the lowercased report. Keywords are a
# LIST (duplicates counted, no dedup). score = matched/total (round 2dp), pass >=0.4.
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/DEPENDENCY_TRACE.md"
GT="${TASK_DIR:-$(dirname "$(dirname "$0")")}/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DEPENDENCY_TRACE.md not found"}\n'
  exit 0
fi

if [[ ! -f "$GT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "ground_truth.json not found"}\n'
  exit 0
fi

report_lc=$(tr '[:upper:]' '[:lower:]' < "$REPORT")

total=$(jq '(.integration_path // []) | length' "$GT")
if [[ "$total" -eq 0 ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "No integration path in GT"}\n'
  exit 0
fi

matched=0
for ((i = 0; i < total; i++)); do
  step=$(jq -r ".integration_path[$i]" "$GT")
  kw_total=0
  kw_hit=0
  # str.split() on whitespace; -f disables globbing so '*' in data stays literal.
  set -f
  for word in $step; do
    if [[ ${#word} -gt 4 ]]; then
      kw=$(printf '%s' "$word" | tr '[:upper:]' '[:lower:]')
      kw_total=$((kw_total + 1))
      if printf '%s' "$report_lc" | grep -qF -- "$kw"; then
        kw_hit=$((kw_hit + 1))
      fi
    fi
  done
  set +f
  # step matched when kw_hit >= kw_total * 0.3  (integer-safe: *10 >= *3)
  if [[ $((kw_hit * 10)) -ge $((kw_total * 3)) ]]; then
    matched=$((matched + 1))
  fi
done

round2() {
  awk -v x="$1" 'BEGIN{ s=sprintf("%.2f", x); sub(/0+$/, "", s); if (s ~ /\.$/) s=s"0"; print s }'
}
raw=$(jq -n --argjson m "$matched" --argjson t "$total" '$m/$t')
score=$(round2 "$raw")
passed=$(jq -rn --argjson s "$score" 'if $s>=0.4 then "true" else "false" end')

printf '{"score": %s, "passed": %s, "reason": "Matched %s/%s integration path steps"}\n' \
  "$score" "$passed" "$matched" "$total"
