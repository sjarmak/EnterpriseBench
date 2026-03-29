#!/usr/bin/env bash
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/BLAST_RADIUS.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "BLAST_RADIUS.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
# BOM / dependency management chain
if grep -qiE 'BOM|bill.of.materials|dependency.management|jackson.bom' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# spring-boot-dependencies or spring-boot-starter-web
if grep -qiE 'spring.boot.dependencies|starter.web|spring.boot.starter' "$REPORT"; then FOUND=$((FOUND + 1)); fi
# dropwizard-jackson module
if grep -qiE 'dropwizard.jackson|dropwizard.*jackson' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d transitive paths"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
