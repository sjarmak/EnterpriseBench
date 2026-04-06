#!/usr/bin/env bash
# Checkpoint 2: Verify agent traced the pull-to-export error chain
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=5

# Must mention moby's pull path (image_pull.go or pullTag or WithPullUnpack)
if grep -qiE 'image_pull\.go|pullTag|WithPullUnpack' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention containerd's client/pull.go or the Unpacker creation
if grep -qiE 'client/pull\.go|client\.Pull|Unpacker|pullCtx\.Unpack' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the unpacker's snapshot check (sn.Stat, sn.Prepare, AlreadyExists, chainID)
if grep -qiE 'sn\.Stat|sn\.Prepare|AlreadyExists|already.*exist.*snapshot|snapshot.*chain' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention content store missing blob / content not fetched
if grep -qiE 'content.*store.*miss|content.*not.*fetch|blob.*miss|layer.*blob.*absent|content.*absent|fetch.*never|blob.*not.*in.*content|layer.*not.*store|content.*without.*blob|no.*blob.*content|layer.*never.*download|blob.*absent' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the export/save path (image_exporter.go, ExportImage, WithSkipMissing, docker save)
if grep -qiE 'image_exporter\.go|ExportImage|WithSkipMissing|docker.*save.*miss|export.*miss|archive.*skip' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 4 ]; then
  PASSED=true
else
  PASSED=false
fi

printf '{"score": %s, "passed": %s, "reason": "Traced %d/%d error chain components"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
