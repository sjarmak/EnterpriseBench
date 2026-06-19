#!/usr/bin/env bash
# check_expected_values.sh — verify agent documents correct root cause for phantom diffs
# Reimplemented in bash+jq+grep (no python3 in container). Weighted scoring
# (files 0.7 + impact 0.3, round to 2dp) and pass logic identical to the previous
# python implementation; detail uses python bool repr (True/False). 'impact'
# length uses python str() length for strings (the realistic case); non-string
# impact values would follow python str() repr length (an unreproduced corner).
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/DRIFT_REPORT.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# python truthiness: present key with a value that is not null/false/0/""/[]/{}.
truthy='(. != null and . != false and . != 0 and . != "" and . != [] and . != {})'

has_core_file=$(jq "any(.drift_points // [] | .[]; has(\"terraform_core_file\") and (.terraform_core_file | $truthy))" "$REPORT")
has_provider_file=$(jq "any(.drift_points // [] | .[]; has(\"provider_file\") and (.provider_file | $truthy))" "$REPORT")
# len(str(impact)) > 10, computed for string impacts (realistic); coded via utf-8 length.
has_impact=$(jq "any(.drift_points // [] | .[]; has(\"impact\") and ((.impact | tostring | length) > 10))" "$REPORT")

# Python bool repr for detail.
[[ "$has_core_file" == true ]] && cf=True || cf=False
[[ "$has_provider_file" == true ]] && pf=True || pf=False
[[ "$has_impact" == true ]] && im=True || im=False

[[ "$has_core_file" == true ]] && core_v=1.0 || core_v=0.0
[[ "$has_provider_file" == true ]] && prov_v=1.0 || prov_v=0.0
[[ "$has_impact" == true ]] && imp_v=0.3 || imp_v=0.0

raw=$(awk "BEGIN {fs=$core_v*0.5+$prov_v*0.5; printf \"%.10f\", fs*0.7+$imp_v}")
score=$(awk "BEGIN {printf \"%.2f\", $raw}")
score=${score%0}; score=${score%.}; case "$score" in *.*) ;; *) score="$score.0";; esac

if [[ "$has_core_file" == true && "$has_provider_file" == true && "$has_impact" == true ]]; then passed=true; else passed=false; fi

printf '{"score": %s, "passed": %s, "detail": "Core file: %s, provider file: %s, impact: %s"}\n' \
  "$score" "$passed" "$cf" "$pf" "$im"
