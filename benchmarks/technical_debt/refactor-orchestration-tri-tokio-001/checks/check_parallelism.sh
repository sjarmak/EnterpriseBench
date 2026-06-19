#!/usr/bin/env bash
# Checkpoint 3: Verify agent correctly identifies parallelizable steps
# Uses bash + jq + grep (no python3 in container — task images ship bash/grep/jq
# but not python/python3, so the previous `python3 -c` body exited 127). Scoring
# semantics are identical to that python implementation, including its literal
# substring matching (Python `term in text`, so 'cannot.*parallel' is matched
# literally, not as a regex).
set -euo pipefail

ANSWER="${WORKSPACE:-/workspace}/REFACTOR_PLAN.md"
GT="${TASK_DIR:-$(dirname "$(dirname "$0")")}/ground_truth.json"

if [[ ! -f "$ANSWER" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "REFACTOR_PLAN.md not found"}\n'
  exit 0
fi

if [[ ! -f "$GT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "ground_truth.json not found"}\n'
  exit 0
fi

answer_lc=$(tr '[:upper:]' '[:lower:]' < "$ANSWER")
has_term() { printf '%s' "$answer_lc" | grep -qF -- "$1"; }

mentions_parallel=false
for t in parallel concurrent simultaneous independent; do
  if has_term "$t"; then mentions_parallel=true; break; fi
done

n_parallel=$(jq '(.parallelizable_steps // []) | length' "$GT")

if [[ "$n_parallel" -eq 0 ]]; then
  seq_match=false
  for t in "sequential" "serial" "no parallel" "cannot.*parallel" "depends on"; do
    if has_term "$t"; then seq_match=true; break; fi
  done
  if $seq_match; then
    score="1.0"; detail="Correctly identified no parallelizable steps (sequential chain)"
  elif $mentions_parallel; then
    score="0.3"; detail="Mentions parallelism but chain is fully sequential"
  else
    score="0.5"; detail="Did not explicitly address parallelism"
  fi
else
  if $mentions_parallel; then
    score="0.8"; detail="Agent addresses parallelism opportunities"
  else
    score="0.2"; detail="Agent did not identify parallelism opportunities"
  fi
fi

passed=$(jq -n --argjson s "$score" 'if $s >= 0.5 then true else false end')
printf '{"score": %s, "passed": %s, "reason": "%s"}\n' "$score" "$passed" "$detail"
