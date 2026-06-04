#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified drift points in external RabbitMQ config
# Reimplemented in bash+jq+grep (no python3 in container); keyword membership
# over the lowercased JSON dump of drift_points, scoring (FOUND/TOTAL, awk %.2f,
# pass at FOUND>=2) identical to the previous python implementation.
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=3

# text = json.dumps(report['drift_points']).lower()
text=$(jq -c '.drift_points // []' "$REPORT" | tr '[:upper:]' '[:lower:]')
has() { printf '%s' "$text" | grep -qF -- "$1"; }

# Check 1: 'secret' and ('key' or 'password')
if has secret && { has key || has password; }; then
  FOUND=$((FOUND + 1))
fi

# Check 2: 'password' and ('optional' or 'required' or 'unnecessary' or 'external')
if has password && { has optional || has required || has unnecessary || has external; }; then
  FOUND=$((FOUND + 1))
fi

# Check 3: 'erlang' or 'cookie' or ('inconsisten' and ('database' or 'db' or 'rabbitmq'))
if has erlang || has cookie || { has inconsisten && { has database || has db || has rabbitmq; }; }; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d drift categories"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
