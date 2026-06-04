#!/usr/bin/env bash
# Checkpoint 2: Verify agent determined correct expected values per drift point
# Reimplemented in bash+jq+grep (no python3 in container); scoring (FOUND/TOTAL,
# awk %.2f, pass at FOUND>=1) identical to the previous python implementation.
# (Realistic reports carry string key/file/expected; a non-string value would
# make python's .lower()/+ raise — an unreproduced corner, not present in data.)
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=2

# Per drift point: "<lower(key+file)>\t<lower(expected)>".
mapfile -t rows < <(jq -r '
  .drift_points // [] | .[] |
  (((.key // "") + (.file // "")) | ascii_downcase) + "\t" + ((.expected // "") | ascii_downcase)
' "$REPORT")

match_pair() { # needle present in both key-side and expected-side of some point
  local needle="$1" row k e
  for row in "${rows[@]}"; do
    k="${row%%$'\t'*}"; e="${row#*$'\t'}"
    if [[ "$k" == *"$needle"* && "$e" == *"$needle"* ]]; then return 0; fi
  done
  return 1
}

# serflan-udp should use containerPorts.serfLAN
if match_pair serflan; then FOUND=$((FOUND + 1)); fi
# serfwan-udp should use containerPorts.serfWAN
if match_pair serfwan; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 1 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Correct expected values for %d/%d drift points"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
