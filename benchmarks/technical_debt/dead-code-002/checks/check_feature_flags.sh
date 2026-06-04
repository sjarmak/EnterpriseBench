#!/usr/bin/env bash
# check_feature_flags.sh — Verify feature flag identification.
# Env: WORKSPACE, TASK_DIR, TASK_ID
set -euo pipefail

REPORT="${WORKSPACE}/react/dead_code_report.json"
GT_DIR="${TASK_DIR}/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
    echo '{"score": 0.0, "detail": "No dead_code_report.json found"}'
    exit 0
fi

# bash+jq+grep (no python3 in container). Semantics identical to the prior python3:
# gt_flag_names = set of lowercased gt.feature_flags[].flag ; if empty → score 1.0;
# else for each claimed item build "evidence symbol file" (all lowercased, .get default
# ""), and a flag is "found" when it appears as a literal substring; score = recall =
# |found| / |gt_flag_names|, rounded 4dp; detail lists found flags sorted (or "none").
# (No ground-truth-missing guard — like the original, a missing GT aborts the script.)

# Unique lowercased flag names (python set of f["flag"].lower()).
gt_flag_names=$(jq -r '(.feature_flags // []) | map(.flag | ascii_downcase) | unique | .[]' "$GT_DIR")
gt_count=$(printf '%s' "$gt_flag_names" | grep -c . || true)

if [[ "$gt_count" -eq 0 ]]; then
    echo '{"score": 1.0, "detail": "No feature flags in ground truth"}'
    exit 0
fi

# Per-item combined haystack "evidence symbol file", lowercased (.get default "").
mapfile -t combined < <(jq -r '
  .[] | ( (.evidence // "") + " " + (.symbol // "") + " " + (.file // "") )
      | ascii_downcase' "$REPORT")

# A flag is found if it is a literal substring of ANY item haystack.
found=""
while IFS= read -r flag; do
    [[ -z "$flag" ]] && continue
    for hay in "${combined[@]}"; do
        if printf '%s' "$hay" | grep -qF -- "$flag"; then
            found+="$flag"$'\n'
            break
        fi
    done
done <<< "$gt_flag_names"

found_sorted=$(printf '%s' "$found" | sed '/^$/d' | LC_ALL=C sort)
found_count=$(printf '%s' "$found_sorted" | grep -c . || true)
joined=$(printf '%s' "$found_sorted" | paste -sd, - | sed 's/,/, /g')
[[ -z "$joined" ]] && joined="none"

score=$(awk -v f="$found_count" -v t="$gt_count" 'BEGIN{printf "%.10f", f/t}')
pyfloat() { printf '%.*f' "$2" "$1" | sed -e 's/0*$//' -e 's/\.$/.0/'; }
score_r=$(pyfloat "$score" 4)
printf '{"score": %s, "detail": "flags_found=%s/%s (%s)"}\n' "$score_r" "$found_count" "$gt_count" "$joined"
