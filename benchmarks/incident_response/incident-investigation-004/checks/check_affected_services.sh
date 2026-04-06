#!/usr/bin/env bash
# Checkpoint 3: Verify agent listed affected components
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4

# Must mention moby image pull (daemon/containerd/image_pull.go or pullTag)
if grep -qiE 'image_pull\.go|daemon/containerd.*pull|pullTag' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention containerd unpacker (pkg/unpack/unpacker.go or unpack package)
if grep -qiE 'unpacker\.go|pkg/unpack|unpack.*package' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention content store as affected subsystem
if grep -qiE 'content.*store|content\.Store|content.*service' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention the export/save path or snapshotter as separate component
if grep -qiE 'image_exporter\.go|ExportImage|snapshotter|snapshot.*service' "$REPORT"; then
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

printf '{"score": %s, "passed": %s, "reason": "Identified %d/%d affected components"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
