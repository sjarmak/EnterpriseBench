#!/usr/bin/env bash
# Checkpoint 4: Verify agent proposed correct remediation
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/moby/INCIDENT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "INCIDENT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=2

# Must mention not using WithPullUnpack for local/overlayfs snapshotters, or only for remote snapshotters
if grep -qiE '(WithPullUnpack).{0,60}(avoid|omit|skip|not.*use|remove|disable|only|conditional|restrict|overlayfs|local.*snap)|(avoid|omit|skip|not.*use|remove|disable|restrict).{0,40}(WithPullUnpack)|WithPullUnpack.*only.*remote|local.*snapshot.*not.*unpack' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

# Must mention ensuring content/blobs are always fetched/available regardless of snapshot state
if grep -qiE '(content|blob|layer).{0,40}(always|even.*snap|regardless|independent|whether.*snap|not.*depend)|(decouple|separate).{0,40}(content|blob).{0,40}(snap)|always.*fetch.*content|always.*fetch.*blob|ensure.*content.*fetch|fetch.*regardless.*snapshot|blob.*always.*store' "$REPORT"; then
  FOUND=$((FOUND + 1))
fi

if [ "$TOTAL" -gt 0 ]; then
  SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
else
  SCORE="0.00"
fi
if [ "$FOUND" -ge 1 ]; then
  PASSED=true
else
  PASSED=false
fi

printf '{"score": %s, "passed": %s, "reason": "Remediation quality: %d/%d key elements"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
