#!/usr/bin/env bash
# Checkpoint 3: Verify parallelization claims are correct
# Uses bash + jq + grep (no python3 in container — task images ship bash/grep/jq
# but not python/python3, so the previous `python3 -c` body exited 127). Scoring
# semantics are identical to that python implementation: parallel sections are
# extracted with the same regex, tokens with the same [@\w/.-]+ pattern, and the
# recall/correctness/violation arithmetic and round(score,2) are preserved.
set -euo pipefail

ANSWER="${WORKSPACE:-/workspace}/REFACTOR_PLAN.md"
GT="${TASK_DIR:-$(dirname "$(dirname "$0")")}/ground_truth.json"

if [[ ! -f "$ANSWER" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "REFACTOR_PLAN.md not found"}\n'
  exit 0
fi

if [[ ! -f "$GT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "ground_truth.json not found"}\n'
  exit 0
fi

# Format whole numbers as python floats (json.dumps prints 1.0/0.0, jq prints 1/0).
pyfloat() {
  local v="$1"
  if [[ "$v" != *.* && "$v" != *e* && "$v" != *E* ]]; then printf '%s.0' "$v"; else printf '%s' "$v"; fi
}

# graph_nodes = keys of dependency_graph
declare -A NODE_SET=()
while IFS= read -r gn; do [[ -n "$gn" ]] && NODE_SET["$gn"]=1; done \
  < <(jq -r '(.dependency_graph // {}) | keys[]' "$GT")

# gt has parallelizable steps?
n_gt_groups=$(jq '(.parallelizable_steps // []) | length' "$GT")

# Extract parallel sections. Python uses re.findall with the regex below (IGNORECASE)
# and keeps capture group 1 — the text after each keyword plus indented -/* continuation
# lines. We extract the same regions with grep -ozP (PCRE, \n matchable via null-data)
# and read tokens directly from them. We deliberately keep the matched keyword words in
# the extracted text: the only tokens this adds are the keywords themselves
# (parallel/concurrent/independent/simultaneously), and none of those is ever a repo
# node in any ground_truth (verified), so the set of claimed repos — and the duplicate
# multiset used for violation counting — is identical to python's group(1) tokenisation.
PAR_RX='(?i)(?:parallel|concurrent|independent|simultaneously)[:\s]*[^\n]+(?:\n\s*[-*]\s*[^\n]+)*'

MATCHES=$(grep -aozP "$PAR_RX" "$ANSWER" 2>/dev/null | tr '\0' '\n' || true)

# A section "exists" iff re.findall returned >=1 match (python truthiness of the list).
if [[ -n "$MATCHES" ]]; then has_section=true; else has_section=false; fi

joined="$MATCHES"

emit() { printf '{"score": %s, "passed": %s, "reason": "%s"}\n' "$1" "$2" "$3"; }

if [[ "$has_section" == "false" && "$n_gt_groups" -eq 0 ]]; then
  emit "1.0" "true" "No parallelism expected or claimed"
  exit 0
fi
if [[ "$has_section" == "false" && "$n_gt_groups" -ne 0 ]]; then
  emit "0.2" "false" "Agent did not identify parallelizable steps"
  exit 0
fi

# --- there is at least one section. Extract claimed repos (tokens that are nodes). ---
# tokens via python r'[@\w/.-]+' where \w = [A-Za-z0-9_].
mapfile -t tokens < <(printf '%s' "$joined" | grep -oP '[@\w/.-]+' 2>/dev/null || true)

# claimed = ordered tokens that are graph nodes (python list, may contain dups)
claimed=()
declare -A CLAIMED_SET=()
for t in "${tokens[@]}"; do
  if [[ -n "${NODE_SET[$t]+x}" ]]; then
    claimed+=("$t")
    CLAIMED_SET["$t"]=1
  fi
done

# count violations: for each claimed repo, for each of its deps, if dep in claimed.
# Python "section but no gt" branch iterates `claimed` (the LIST, with dups);
# the "both" branch iterates `claimed_repos` (the SET). Handle separately.

if [[ "$n_gt_groups" -eq 0 ]]; then
  # branch: section exists, no gt_parallel. Iterate claimed LIST.
  violations=0
  for repo in "${claimed[@]}"; do
    while IFS= read -r dep; do
      [[ -z "$dep" ]] && continue
      if [[ -n "${CLAIMED_SET[$dep]+x}" ]]; then violations=$((violations + 1)); fi
    done < <(jq -r --arg r "$repo" '(.dependency_graph[$r] // [])[]' "$GT")
  done
  if [[ "$violations" -eq 0 ]]; then
    emit "0.8" "true" "Parallel claims are valid (no dependency violations)"
  else
    score=$(jq -n --argjson v "$violations" '[0.0, (1.0 - $v*0.3)] | max')
    passed=$(jq -n --argjson s "$score" 'if $s >= 0.5 then true else false end')
    emit "$(pyfloat "$score")" "$passed" "${violations} dependency violations in parallel claims"
  fi
  exit 0
fi

# --- both branch: section exists AND gt_parallel non-empty ---
# claimed_repos = SET of claimed. Dedup preserving membership.
mapfile -t claimed_repos < <(printf '%s\n' "${claimed[@]}" | awk 'NF' | sort -u)

# gt_all_parallel = union of all groups
mapfile -t gt_all < <(jq -r '(.parallelizable_steps // [])[][]' "$GT" | sort -u)
declare -A GT_ALL_SET=()
for g in "${gt_all[@]}"; do [[ -n "$g" ]] && GT_ALL_SET["$g"]=1; done
n_gt_all=${#gt_all[@]}

# overlap = claimed_repos ∩ gt_all
overlap=0
for r in "${claimed_repos[@]}"; do
  [[ -z "$r" ]] && continue
  if [[ -n "${GT_ALL_SET[$r]+x}" ]]; then overlap=$((overlap + 1)); fi
done

# recall
if [[ "$n_gt_all" -gt 0 ]]; then
  recall=$(jq -n --argjson o "$overlap" --argjson n "$n_gt_all" '$o/$n')
else
  recall="1.0"
fi

# violations over the SET claimed_repos
violations=0
for repo in "${claimed_repos[@]}"; do
  [[ -z "$repo" ]] && continue
  while IFS= read -r dep; do
    [[ -z "$dep" ]] && continue
    if [[ -n "${CLAIMED_SET[$dep]+x}" ]]; then violations=$((violations + 1)); fi
  done < <(jq -r --arg r "$repo" '(.dependency_graph[$r] // [])[]' "$GT")
done

if [[ "$violations" -eq 0 ]]; then
  correctness="1.0"
else
  correctness=$(jq -n --argjson v "$violations" '[0.0, (1.0 - $v*0.3)] | max')
fi

# score = recall*0.6 + correctness*0.4, round 2
score=$(jq -n --argjson r "$recall" --argjson c "$correctness" '((($r*0.6 + $c*0.4) * 100) | round) / 100')
passed=$(jq -n --argjson s "$score" 'if $s >= 0.5 then true else false end')

# reason: f'Recall={recall:.2f}, correctness={correctness:.2f}'
recall_2dp=$(printf '%.2f' "$recall")
corr_2dp=$(printf '%.2f' "$correctness")
emit "$(pyfloat "$score")" "$passed" "Recall=${recall_2dp}, correctness=${corr_2dp}"
