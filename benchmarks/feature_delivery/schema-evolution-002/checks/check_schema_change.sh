#!/usr/bin/env bash
# Checkpoint 1: Verify agent identifies the new RealmExport model and migration
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/zulip/SCHEMA_IMPACT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "SCHEMA_IMPACT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2
if grep -qE '0595.*realmexport|add_realmexport' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qE 'models/realms\.py|RealmExport' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d schema change elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
