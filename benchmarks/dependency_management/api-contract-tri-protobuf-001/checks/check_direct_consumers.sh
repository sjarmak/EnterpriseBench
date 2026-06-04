#!/usr/bin/env bash
# check_direct_consumers.sh — verify agent finds gRPC and googleapis consumers
# Reimplemented in bash+jq+grep (no python3 in container — the task image ships
# bash/grep/jq but not python3, so the previous `python3 -c` body exited 127).
# Scoring is identical: a repo is "covered" when any of its GT files (full path or
# basename) appears in json.dumps(answer).lower(), or a repo-specific keyword does;
# score = covered-repos / 2, pass only when BOTH repos are covered.
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

# Missing ground_truth.json crashed the original python (FileNotFoundError, rc=1,
# no score line) — preserve that infra-failure signal rather than emit a fake score.
if [[ ! -f "$GT_FILE" ]]; then
  echo "ground_truth.json not found: $GT_FILE" >&2
  exit 1
fi

# json.dumps(answer).lower() — python default separators ", " / ": " (with spaces).
answer_text=$(jq -c . "$ANSWER_FILE" | sed 's/,/, /g; s/:/: /g' | tr '[:upper:]' '[:lower:]')

count_repo_files() {  # $1 = repo name -> echoes count of matching GT files
  local repo="$1" n=0 f fl bl
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    fl=$(printf '%s' "$f" | tr '[:upper:]' '[:lower:]')
    bl=$(printf '%s' "${f##*/}" | tr '[:upper:]' '[:lower:]')
    if [[ "$answer_text" == *"$fl"* || "$answer_text" == *"$bl"* ]]; then
      n=$((n + 1))
    fi
  done < <(jq -r --arg r "$repo" '
    ((.required_files // []) + (.sufficient_files // []))
    | .[] | select(.repo == $r) | .path' "$GT_FILE")
  echo "$n"
}

has_term() { [[ "$answer_text" == *"$1"* ]]; }

grpc_found=$(count_repo_files grpc)
if [[ "$grpc_found" -gt 0 ]] || has_term grpc; then has_grpc=true; else has_grpc=false; fi

gapi_found=$(count_repo_files googleapis)
if [[ "$gapi_found" -gt 0 ]] || has_term googleapis; then has_gapi=true; else has_gapi=false; fi

covered=0
$has_grpc && covered=$((covered + 1))
$has_gapi && covered=$((covered + 1))
case "$covered" in
  0) score="0.0" ;;
  1) score="0.5" ;;
  2) score="1.0" ;;
esac
if $has_grpc && $has_gapi; then passed=true; else passed=false; fi

pg=$($has_grpc && echo True || echo False)
pa=$($has_gapi && echo True || echo False)
printf '{"score": %s, "passed": %s, "detail": "gRPC refs: %s (%s files), googleapis refs: %s (%s files)"}\n' \
    "$score" "$passed" "$pg" "$grpc_found" "$pa" "$gapi_found"
