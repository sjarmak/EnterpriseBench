#!/usr/bin/env bash
# check_drift_points.sh — verify agent identified drift points between Terraform core and AWS provider
# Reimplemented in bash+jq+grep (no python3 in container). Weighted scoring
# (repos 0.6 + concepts 0.4, round to 2dp) and pass logic identical to the
# previous python implementation; detail uses python bool repr (True/False).
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/DRIFT_REPORT.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# Lowercased JSON dump of drift_points (any(c in dumps(p)) over the array equals
# substring search over the whole array dump for these short tokens).
points_text=$(jq -c '.drift_points // []' "$REPORT" | tr '[:upper:]' '[:lower:]')
has() { printf '%s' "$points_text" | grep -qF -- "$1"; }

if has terraform_core || has eval_diff || has eval_refresh; then has_core=True; else has_core=False; fi
if has provider || has aws; then has_provider=True; else has_provider=False; fi

matched=0
for c in json normaliz policy security_group phantom set list ordering default; do
  if has "$c"; then matched=$((matched + 1)); fi
done

[[ "$has_core" == True ]] && core_v=1.0 || core_v=0.0
[[ "$has_provider" == True ]] && prov_v=1.0 || prov_v=0.0

raw=$(awk "BEGIN {rs=$core_v*0.5+$prov_v*0.5; cs=$matched/3.0; if(cs>1.0)cs=1.0; printf \"%.10f\", rs*0.6+cs*0.4}")
score=$(awk "BEGIN {printf \"%.2f\", $raw}")
score=${score%0}; score=${score%.}; case "$score" in *.*) ;; *) score="$score.0";; esac

if [[ "$has_core" == True && "$has_provider" == True && "$matched" -ge 2 ]]; then passed=true; else passed=false; fi

printf '{"score": %s, "passed": %s, "detail": "Core referenced: %s, provider referenced: %s, concepts matched: %d/9"}\n' \
  "$score" "$passed" "$has_core" "$has_provider" "$matched"
