#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# OpenSSL -> curl -> git chain
if grep -qiE 'curl.*git|git.*curl|openssl.*curl' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Python ssl / Node crypto ecosystem path
if grep -qiE 'python.*ssl|ssl.*module|node.*crypto|CPython' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Linking strategy analysis
if grep -qiE 'dynamic.*link|static.*link|pure.*go|CGO|crypto/tls' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d cross-ecosystem paths"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
