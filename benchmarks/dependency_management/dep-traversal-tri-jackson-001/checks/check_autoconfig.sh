#!/usr/bin/env bash
# Checkpoint 3: Verify agent maps Spring Boot autoconfiguration to Jackson module registration
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/DEPENDENCY_TRACE.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DEPENDENCY_TRACE.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qiE 'JacksonAutoConfiguration' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'Jackson2ObjectMapperBuilderCustomizer|ObjectMapperBuilderCustomizer' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'registerModule|register.*module' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE '@ConditionalOn|@AutoConfiguration|@Configuration' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d autoconfiguration concepts"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
