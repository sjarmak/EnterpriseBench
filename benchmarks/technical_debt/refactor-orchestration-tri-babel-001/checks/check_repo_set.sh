#!/usr/bin/env bash
# check_repo_set.sh — checkpoint "identify_repos"
#
# The old check grepped REFACTOR_PLAN.md for 'babel', 'webpack' and 'next' and
# scored found/3. instruction.md lists all three repo paths, so naming them
# proved nothing and a `cp instruction.md REFACTOR_PLAN.md` copy scored 1.0.
#
# Worse, it graded pure RECALL on a question whose answer is precision. The repo
# set is given; what is not given is which of the three the Babel parser change
# actually reaches. webpack v5.88.2 does not parse with Babel at all — it
# declares acorn ^8.7.1 and has no babel package in dependencies (only
# @babel/core and babel-loader as devDependencies, tooling for its own tests) —
# so scheduling webpack work is the wrong answer, and the old check paid for it.
#
# Credit now requires the affected set (babel and next.js) AND the evidence that
# webpack was excluded on purpose: 'acorn', ZERO hits in instruction.md. Naming
# the repos gates but pays nothing on its own (EnterpriseBench-jn73.2.7.3.1.2).
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

# Fixed-string containment, never a regex.
missing = [t for t in tokens if t.lower() not in text]
if missing:
    verdict(0.0,
            "Repo set is prompt-supplied and pays nothing alone: plan never cites "
            "what webpack actually parses with (%s), so nothing here shows the "
            "manifests were read rather than the toolchain recited"
            % (", ".join(missing),))

affected = ["babel", "next"]
found = [r for r in affected if r in text]
score = len(found) / len(affected)
verdict(score,
        "Manifest evidence cited; affected repos identified %d/%d (%s)"
        % (len(found), len(affected), ",".join(found) or "none"))
'
