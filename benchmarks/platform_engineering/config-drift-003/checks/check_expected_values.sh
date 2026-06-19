#!/usr/bin/env bash
# Checkpoint 2: Verify agent correctly identified root cause as Helm include re-evaluation
# Reimplemented in bash+jq+grep (no python3 in container); keyword membership and
# scoring (FOUND/TOTAL, awk %.2f, pass at FOUND>=1) identical to the previous
# python implementation.
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=2

# Check 1 text: root_cause (string) concatenated with compact dump of drift_points.
text1=$( { jq -r '.root_cause // ""' "$REPORT"; jq -c '.drift_points // []' "$REPORT"; } | tr -d '\n' | tr '[:upper:]' '[:lower:]')
# Check 2 text: compact dump of the whole report.
text2=$(jq -c '.' "$REPORT" | tr '[:upper:]' '[:lower:]')
h1() { printf '%s' "$text1" | grep -qF -- "$1"; }
h2() { printf '%s' "$text2" | grep -qF -- "$1"; }

# Check 1: include/template re-evaluation language
if h1 re-evaluat || h1 regenerat || h1 re-run || h1 "each time" || h1 "every call" || h1 "each call" || h1 non-idempotent || h1 "not idempotent"; then
  FOUND=$((FOUND + 1))
fi

# Check 2: password should be consistent/stored/reused
if h2 consistent || h2 store || h2 reuse || h2 single || h2 "same password" || h2 once; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 1 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Root cause correctness: %d/%d checks passed"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
