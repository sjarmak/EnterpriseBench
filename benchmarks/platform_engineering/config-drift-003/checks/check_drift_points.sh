#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified password drift across template includes
# Reimplemented in bash+jq+grep (no python3 in container); scoring identical to
# the previous python implementation (FOUND/TOTAL, awk %.2f, pass at FOUND>=2).
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=3

points_text=$(jq -c '.drift_points // []' "$REPORT" | tr '[:upper:]' '[:lower:]')
report_text=$(jq -c '.' "$REPORT" | tr '[:upper:]' '[:lower:]')
hasp() { printf '%s' "$points_text" | grep -qF -- "$1"; }
hasr() { printf '%s' "$report_text" | grep -qF -- "$1"; }

# Check 1: 'password' and (different/random/regenerat/re-evaluat/mismatch)
if hasp password && { hasp different || hasp random || hasp regenerat || hasp re-evaluat || hasp mismatch; }; then
  FOUND=$((FOUND + 1))
fi

# Check 2: at least 2 distinct non-empty 'file' values among drift points
distinct_files=$(jq -r '[.drift_points // [] | .[] | .file // "" | select(. != "")] | unique | length' "$REPORT")
if [[ "$distinct_files" -ge 2 ]]; then
  FOUND=$((FOUND + 1))
fi

# Check 3 (over full report dump): 'helper' or '_helpers' or 'redis.password' or 'include'
if hasr helper || hasr _helpers || hasr redis.password || hasr include; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d drift indicators"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
