#!/usr/bin/env bash
# Checkpoint 2: Verify agent correctly determined that null overrides should be removed
# Reimplemented in bash+jq+grep (no python3 in container); keyword membership over
# the lowercased full report dump, scoring (FOUND/TOTAL, awk %.2f, pass at
# FOUND>=1) identical to the previous python implementation. NOTE: the 'let.*default'
# term is a LITERAL python substring (not a regex) — matched with grep -F.
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/argo-cd/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=2

text=$(jq -c '.' "$REPORT" | tr '[:upper:]' '[:lower:]')
has() { printf '%s' "$text" | grep -qF -- "$1"; }

# Check 1: remove / delete / omit / 'upstream default' / literal 'let.*default'
if has remove || has delete || has omit || has "upstream default" || has "let.*default"; then
  FOUND=$((FOUND + 1))
fi

# Check 2: '3.17' / 'helm version' / strict / validation / tighten
if has 3.17 || has "helm version" || has strict || has validation || has tighten; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 1 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Expected value correctness: %d/%d checks passed"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
