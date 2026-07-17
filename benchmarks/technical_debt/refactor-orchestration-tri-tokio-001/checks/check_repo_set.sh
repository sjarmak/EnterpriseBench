#!/usr/bin/env bash
# check_repo_set.sh — checkpoint "identify_repos"
#
# The old check grepped REFACTOR_PLAN.md for 'tokio', 'hyper' and 'axum' and
# scored found/3. instruction.md lists all three repo paths, so a plan that
# merely restated the prompt scored 1.0 here with no repo access whatsoever.
#
# The repo SET is given by the prompt and can never be evidence here. What is
# not given is why each repo is in scope. axum is the one that matters: general
# knowledge of the Rust ecosystem says axum reaches tokio through hyper, but
# axum/Cargo.toml declares tokio ITSELF at version "1.25.0", so the tokio change
# reaches axum directly and would still reach it if hyper were deleted. Naming
# all three repos AND citing that requirement is what separates a plan that read
# the manifests from one that recited the ecosystem.
#
# "1.25.0" appears ZERO times in instruction.md, which no longer states any
# version at all (EnterpriseBench-jn73.2.7.3.1.2).
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
ANSWER="$WORKSPACE/REFACTOR_PLAN.md"
GT="${TASK_DIR:-$(dirname "$(dirname "$0")")}/ground_truth.json"
MAX_ANSWER_BYTES=1048576

verdict() { printf '{"score": %s, "passed": %s, "detail": "%s"}\n' "$1" "$2" "$3"; exit 0; }

if [[ ! -f "$GT" ]]; then
  verdict 0.0 false "VERIFIER_INFRA_ERROR: ground_truth.json not found at $GT"
fi
if [[ -L "$ANSWER" ]]; then
  verdict 0.0 false "REFACTOR_PLAN.md is a symlink, not a regular file"
fi
if [[ ! -f "$ANSWER" ]]; then
  verdict 0.0 false "REFACTOR_PLAN.md not found"
fi
if [[ "$(wc -c <"$ANSWER")" -gt "$MAX_ANSWER_BYTES" ]]; then
  verdict 0.0 false "REFACTOR_PLAN.md exceeds ${MAX_ANSWER_BYTES} bytes"
fi

export ANSWER GT
python3 -c '
import json, os

def verdict(score, detail):
    print(json.dumps({"score": round(score, 2), "passed": score >= 0.5, "detail": detail}))
    raise SystemExit(0)

with open(os.environ["GT"]) as fh:
    gt = json.load(fh)

tokens = (gt.get("scoring_evidence") or {}).get("identify_repos") or []
if not tokens:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no identify_repos evidence in ground_truth.json")

with open(os.environ["ANSWER"], encoding="utf-8", errors="replace") as fh:
    text = fh.read().lower()

repos = ["tokio", "hyper", "axum"]
found_repos = [r for r in repos if r in text]
# Fixed-string containment, never a regex: a "." in "1.25.0" would match "1x25y0".
missing = [t for t in tokens if t.lower() not in text]

# The repo set GATES but never pays. instruction.md lists all three paths, so
# crediting the names alone pays a `cp instruction.md REFACTOR_PLAN.md` copy 1.0
# -- which is exactly what the old check did, and why this task was quarantined.
# Naming the repos is necessary and worth nothing on its own; the manifest
# requirement that puts axum directly in scope is the evidence being scored.
if missing:
    verdict(0.0,
            "Repo set is prompt-supplied and pays nothing alone: plan never cites "
            "the tokio requirement axum declares (%s), so nothing here shows the "
            "manifests were read (repos named: %s)"
            % (", ".join(missing), ",".join(found_repos) or "none"))

score = len(found_repos) / len(repos)
verdict(score,
        "Manifest evidence cited; repos identified %d/%d (%s)"
        % (len(found_repos), len(repos), ",".join(found_repos) or "none"))
'
