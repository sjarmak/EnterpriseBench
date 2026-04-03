#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified key packages/classes in all three repos
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/DEPENDENCY_TRACE.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DEPENDENCY_TRACE.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=3
if grep -qiE 'ObjectMapper|jackson-databind' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'MappingJackson2HttpMessageConverter|Jackson2ObjectMapperBuilder' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'JacksonAutoConfiguration|autoconfigure.*jackson' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge "$TOTAL" ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d key packages across repos"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
