#!/usr/bin/env bash
# Checkpoint 1: Verify agent identified drift points (set precision/recall)
# Reimplemented in bash+jq+grep (no python3 in container); scoring semantics
# (FOUND/TOTAL with awk %.2f, pass at FOUND>=2) are identical to the previous
# python implementation.
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# Expected drift points: serflan-udp and serfwan-udp port mismatches
export FOUND=0
export TOTAL=2

# Check if agent identified the serflan-udp port drift. For each drift point,
# f = file + key; matches when lowercased f contains 'serflan'/'serf_lan' or
# raw f contains 'serfLAN' (last clause is case-sensitive — preserved).
if jq -e '
  (.drift_points // []) | any(
    ((.file // "") + (.key // "")) as $f
    | ($f | ascii_downcase | contains("serflan"))
      or ($f | ascii_downcase | contains("serf_lan"))
      or ($f | contains("serfLAN"))
  )' "$REPORT" >/dev/null 2>&1; then
  FOUND=$((FOUND + 1))
fi

# Check if agent identified the serfwan-udp port drift.
if jq -e '
  (.drift_points // []) | any(
    ((.file // "") + (.key // "")) as $f
    | ($f | ascii_downcase | contains("serfwan"))
      or ($f | ascii_downcase | contains("serf_wan"))
      or ($f | contains("serfWAN"))
  )' "$REPORT" >/dev/null 2>&1; then
  FOUND=$((FOUND + 1))
fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 2 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d drift points"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
