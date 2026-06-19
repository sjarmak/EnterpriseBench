#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the ObjectMapper configuration chain across repos
# Uses bash + jq + grep (no python3 dependency — the task container ships neither
# python nor python3, only bash/grep/jq). Scoring semantics are identical to the
# previous python implementation: for each integration_path step, take its words
# longer than 4 chars (lowercased) as keywords; the step counts as matched when at
# least 40% of those keywords appear as substrings in the lowercased report. The
# checkpoint score is matched/total (rounded to 2dp) and passes at >= 0.4.
set -euf -o pipefail

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

total=$(jq '.integration_path | length' "$GT")
if [[ "$total" -eq 0 ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "No integration path in GT"}\n'
  exit 0
fi

matched=0
for ((i = 0; i < total; i++)); do
  step=$(jq -r ".integration_path[$i]" "$GT")
  kw_total=0
  kw_hit=0
  for word in $step; do
    if [[ ${#word} -gt 4 ]]; then
      kw=$(printf '%s' "$word" | tr '[:upper:]' '[:lower:]')
      kw_total=$((kw_total + 1))
      if printf '%s' "$report_lc" | grep -qF -- "$kw"; then
        kw_hit=$((kw_hit + 1))
      fi
    fi
  done
  # step matched when kw_hit >= kw_total * 0.4  (integer-safe: *10 >= *4)
  if [[ $((kw_hit * 10)) -ge $((kw_total * 4)) ]]; then
    matched=$((matched + 1))
  fi
done

score=$(jq -n --argjson m "$matched" --argjson t "$total" '((($m / $t) * 100) | round) / 100')
passed=$(jq -n --argjson m "$matched" --argjson t "$total" 'if ($m / $t) >= 0.4 then true else false end')
printf '{"score": %s, "passed": %s, "reason": "Matched %s/%s integration path steps"}\n' \
  "$score" "$passed" "$matched" "$total"
