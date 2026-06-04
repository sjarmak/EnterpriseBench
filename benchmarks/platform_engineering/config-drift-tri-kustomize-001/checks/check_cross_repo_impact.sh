#!/usr/bin/env bash
# check_cross_repo_impact.sh — verify agent documented cross-repo impact
# bash+jq+grep (no python3 in container). Scoring semantics identical to the
# previous python implementation.
set -euo pipefail

export REPORT="${WORKSPACE:-/workspace}/DRIFT_REPORT.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# Original python loaded REPORT and GT with no try/except; a missing or
# unparseable file aborts with a traceback (non-zero exit, no stdout). Mirror it.
if [[ ! -f "$GT_FILE" ]] || ! jq -e . "$REPORT" >/dev/null 2>&1 || ! jq -e . "$GT_FILE" >/dev/null 2>&1; then
  exit 1
fi

# Python truthiness for a per-point field: key present AND value not in
# (None, False, "", 0, [], {}). jq's // keeps "" so this is expressed explicitly.
truthy='(. != null and . != false and . != "" and . != 0 and . != [] and . != {})'

has_field() {
  jq -e "any((.drift_points // [])[]?; has(\"$1\") and (.\"$1\" | $truthy))" "$REPORT" >/dev/null 2>&1 \
    && echo 1 || echo 0
}

has_kustomize_file=$(has_field kustomize_source_file)
has_argocd_file=$(has_field argocd_source_file)
has_flux_file=$(has_field flux_source_file)

# has_impact = any('impact' in p and len(str(p['impact'])) > 10)
has_impact=$(jq -e 'any((.drift_points // [])[]?; has("impact") and ((.impact | tostring | length) > 10))' "$REPORT" >/dev/null 2>&1 && echo 1 || echo 0)

file_repos=$((has_kustomize_file + has_argocd_file + has_flux_file))

# score = round((file_repos/3)*0.7 + (0.3 if has_impact else 0.0), 2) banker's rounding
score=$(jq -n --argjson r "$file_repos" --argjson imp "$has_impact" '
  (($r / 3.0) * 0.7 + (if $imp == 1 then 0.3 else 0.0 end)) as $s |
  ($s * 100) as $v | ($v | floor) as $fl | ($v - $fl) as $fr |
  ((if $fr < 0.5 then $fl elif $fr > 0.5 then $fl + 1
    else (if ($fl % 2) == 0 then $fl else $fl + 1 end) end) / 100) | tostring' | tr -d '"')
case "$score" in *.*) ;; *) score="${score}.0";; esac

# passed = file_repos >= 2 and has_impact
if [[ "$file_repos" -ge 2 && "$has_impact" -eq 1 ]]; then passed=true; else passed=false; fi

# detail mirrors python f-string with capitalised bool repr for has_impact.
if [[ "$has_impact" -eq 1 ]]; then imp_repr=True; else imp_repr=False; fi
printf '{"score": %s, "passed": %s, "detail": "Source files from %s/3 repos, impact documented: %s"}\n' \
  "$score" "$passed" "$file_repos" "$imp_repr"
