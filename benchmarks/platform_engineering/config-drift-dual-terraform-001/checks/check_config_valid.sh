#!/usr/bin/env bash
# check_config_valid.sh — verify agent produced valid DRIFT_REPORT.json
# Uses bash + jq + grep (no python3 in container). Scoring identical to the previous
# python: invalid JSON -> 0.0; drift_points missing/empty/non-list -> 0.2; entries with
# a config_key -> 1.0 ("Valid report with N drift points"); none -> 0.3.
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/DRIFT_REPORT.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# Invalid JSON -> mirror python json.JSONDecodeError branch.
if ! jq -e . "$REPORT" >/dev/null 2>&1; then
  printf '{"score": 0.0, "passed": false, "detail": "Invalid JSON in DRIFT_REPORT.json"}\n'
  exit 0
fi

# points = report.get('drift_points', []); empty/missing/non-list -> 0.2
points_len=$(jq -r 'if type=="object" and (.drift_points|type=="array") then (.drift_points|length) else 0 end' "$REPORT")
if [[ "$points_len" -eq 0 ]]; then
  printf '{"score": 0.2, "passed": false, "detail": "drift_points array is empty or missing"}\n'
  exit 0
fi

# valid = count of entries that are objects with a 'config_key' key
valid=$(jq -r '[.drift_points[] | select(type=="object" and has("config_key"))] | length' "$REPORT")
if [[ "$valid" -gt 0 ]]; then
  printf '{"score": 1.0, "passed": true, "detail": "Valid report with %s drift points"}\n' "$valid"
else
  printf '{"score": 0.3, "passed": false, "detail": "drift_points lack config_key field"}\n'
fi
