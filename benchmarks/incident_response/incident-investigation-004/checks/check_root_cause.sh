#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified the root cause file and mechanism
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must identify the unpacker in containerd (pkg/unpack/unpacker.go or unpack package)
if grep -qiE 'unpacker\.go|pkg/unpack|unpack.*package|doUnpackFn' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention snapshot existence check (Stat on chainID or snapshot already exists)
if grep -qiE 'sn\.Stat|snapshot.*exist|snapshot.*already|chainID.*exist|Stat.*chainID|snapshot.*present|already.*unpack|snapshot.*found' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention content/blob fetch being skipped
if grep -qiE 'skip.*fetch|content.*skip|blob.*not.*fetch|fetch.*skip|content.*miss|layer.*not.*download|skip.*content|skip.*blob' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention WithPullUnpack in moby's pull path
if grep -qiE 'WithPullUnpack|image_pull\.go|pullTag' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 3 ]; then
  PASSED=true
else
  PASSED=false
fi

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d root cause elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
