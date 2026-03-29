#!/usr/bin/env bash
# Checkpoint 3: Verify agent traced transitive dependency paths
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# Path: lodash -> webpack (direct, but should be documented as a path)
if grep -qiE 'lodash.*webpack|webpack.*lodash' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Path: lodash -> jest-haste-map -> jest (transitive)
if grep -qiE 'jest.haste.map|haste-map' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Path: lodash -> babel-loader or @babel/traverse -> webpack (transitive)
if grep -qiE 'babel.loader|@babel.*webpack|traverse.*webpack' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d transitive paths"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
