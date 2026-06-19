#!/usr/bin/env bash
# Checkpoint 2: Verify agent determined correct expected values for each drift point
# Reimplemented in bash+jq+grep (no python3 in container); per-point keyword
# logic and scoring (FOUND/TOTAL, awk %.2f, pass at FOUND>=1) identical to the
# previous python implementation.
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/charts/DRIFT_REPORT.json"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

export FOUND=0
export TOTAL=2

# Per drift point: "<lower(expected)>\t<lower(key)>".
mapfile -t rows < <(jq -r '
  .drift_points // [] | .[] |
  ((.expected // "") | ascii_downcase) + "\t" + ((.key // "") | ascii_downcase)
' "$REPORT")

# Check 1: (optional|not required|not mandatory in expected AND password in key+expected)
#          OR (existing AND secret in expected)
c1=false
for row in "${rows[@]:-}"; do
  [[ -z "${rows[*]:-}" ]] && break
  e="${row%%$'\t'*}"; k="${row#*$'\t'}"
  if { [[ "$e" == *optional* || "$e" == *"not required"* || "$e" == *"not mandatory"* ]] && [[ "$k$e" == *password* ]]; }; then c1=true; break; fi
  if [[ "$e" == *existing* && "$e" == *secret* ]]; then c1=true; break; fi
done
[[ "$c1" == true ]] && FOUND=$((FOUND + 1))

# Check 2: combined = expected+' '+key; 'key' in combined AND 'secret' in combined
c2=false
for row in "${rows[@]:-}"; do
  [[ -z "${rows[*]:-}" ]] && break
  e="${row%%$'\t'*}"; k="${row#*$'\t'}"
  combined="$e $k"
  if [[ "$combined" == *key* && "$combined" == *secret* ]]; then c2=true; break; fi
done
[[ "$c2" == true ]] && FOUND=$((FOUND + 1))

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 1 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Correct expected values for %d/%d key drift points"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
