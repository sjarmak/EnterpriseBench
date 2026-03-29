#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified affected packages
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/pnpm/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=9
if grep -qiE 'lockfile.file|lockfile-file' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'lockfile.utils|lockfile-utils' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'lockfile.to.pnp|lockfile-to-pnp' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'merge.lockfile|merge-lockfile' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'prune.lockfile|prune-lockfile' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'filter.lockfile|filter-lockfile' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'calc.dep.state|calc-dep-state' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'plugin.commands.rebuild|plugin-commands-rebuild' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'audit' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Compute score as proper decimal
if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 6 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d affected packages"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
