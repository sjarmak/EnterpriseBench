#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# Spring Boot starter path
if grep -qiE 'starter.log4j2|spring.boot.starter.*log4j|log4j2.*starter' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# Kafka dependency path
if grep -qiE 'kafka.*log4j|log4j.*kafka|kafka.clients' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# JNDI lookup mechanism
if grep -qiE 'JNDI|lookup|remote.code|RCE' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d transitive paths"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
