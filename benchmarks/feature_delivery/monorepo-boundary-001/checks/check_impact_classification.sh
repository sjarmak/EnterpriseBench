#!/usr/bin/env bash
# Checkpoint 2: Verify impact classification
# Implemented in bash+jq+grep (no python3 in container). Scoring identical to the
# previous python3 implementation: three regex signals over the lowercased report
# (construct=TSPropertySignature|initializer, semver=\bpatch\b,
# package=@babel/types|babel[/-]types); score=matched/3 (round 2dp), pass at >=2.
# The reason string reproduces python's list repr (single quotes) of found/missing.
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/babel/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

content=$(tr '[:upper:]' '[:lower:]' < "$REPORT")

sig() { printf '%s' "$content" | grep -Eq -- "$1"; }

construct=false; sig 'tspropertysignature|initializer' && construct=true
semver=false;    sig '\bpatch\b'                       && semver=true
package=false;   sig '@babel/types|babel[/-]types'     && package=true

matched=0
found_parts=()
missing_parts=()
# dict order: construct, semver, package
for kv in "construct:$construct" "semver:$semver" "package:$package"; do
  k="${kv%%:*}"; v="${kv#*:}"
  if [[ "$v" == true ]]; then
    matched=$((matched + 1))
    found_parts+=("'$k'")
  else
    missing_parts+=("'$k'")
  fi
done

# python list repr: [] when empty, ['a', 'b'] (elements joined by ", ") otherwise.
join_list() {
  if [[ $# -eq 0 ]]; then printf '[]'; return; fi
  local out="$1"; shift
  local e
  for e in "$@"; do out="${out}, ${e}"; done
  printf '[%s]' "$out"
}
found_repr=$(join_list "${found_parts[@]}")
missing_repr=$(join_list "${missing_parts[@]}")

round2() {
  awk -v x="$1" 'BEGIN{ s=sprintf("%.2f", x); sub(/0+$/, "", s); if (s ~ /\.$/) s=s"0"; print s }'
}
raw=$(jq -n --argjson m "$matched" '$m/3.0')
score=$(round2 "$raw")
passed=$([[ "$matched" -ge 2 ]] && echo true || echo false)

reason="Matched ${matched}/3 required signals (found: ${found_repr}; missing: ${missing_repr})"
printf '{"score": %s, "passed": %s, "reason": "%s"}\n' "$score" "$passed" "$reason"
