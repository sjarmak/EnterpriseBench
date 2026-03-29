#!/usr/bin/env bash
# Checkpoint 3: Verify agent describes attack vectors
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/security_audit.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "security_audit.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3

# Whitespace smuggling
if grep -qiE 'smuggl|non.standard.*whitespace|tab.*char|zero.width' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# Token injection
if grep -qiE 'inject|malform.*token|invalid.*char' "$REPORT"; then FOUND=$((FOUND + 1)); fi

# General attack description
if grep -qiE 'attack.*vector|exploit|bypass|vulnerab' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Attack vectors: %d/%d elements found"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
