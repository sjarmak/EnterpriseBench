#!/usr/bin/env bash
# check_repo_set.sh — checkpoint "identify_repos"
#
# The old check grepped REFACTOR_PLAN.md for 'preset-env', 'preset-react',
# 'plugin-transform-react', 'plugin-transform-property-mutators' and
# '@babel/core' and scored found/5. instruction.md states the first four
# outright, so a `cp instruction.md REFACTOR_PLAN.md` copy scored 0.8 here.
#
# Worse, all five grep targets were the wrong answer. Four of the five packages
# require no work at all: @babel/preset-env does not depend on
# plugin-transform-property-mutators, @babel/preset-react depends on none of the
# three removed react plugins, and @babel/core is only a peerDependency. The one
# package that does consume all four removal targets — @babel/standalone — the
# old key never named. See ground_truth.json:_premise_correction.
#
# The question is precision, not recall: the removal set is given, the consumer
# set is not. Credit now requires 'standalone' (ZERO hits in instruction.md) and
# then pays for refuting the diamond the prompt asserts, package by package
# (EnterpriseBench-jn73.2.7.3.1.2).
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
    text = fh.read()
lowered = text.lower()

# Fixed-string containment, never a regex.
missing = [t for t in tokens if t.lower() not in lowered]
if missing:
    verdict(0.0,
            "Consumer set not evidenced: plan never names the one workspace "
            "package that references the removal targets (%s), so nothing here "
            "shows the manifests were read rather than the prompt restated"
            % (", ".join(missing),))

EXCLUDED = ("not affected", "unaffected", "no change", "no changes", "not require",
            "no work", "out of scope", "not in scope", "excluded", "not impacted",
            "no update", "not need", "does not consume", "not consume",
            "does not depend", "not depend", "no dependency", "does not reference",
            "not reference")

# The refutation must be stated about the package ON ONE LINE. Scanning the whole
# document would credit a plan that names preset-env here and "not affected" in
# an unrelated sentence about something else.
def refuted(pkg):
    return any(pkg in line and any(term in line for term in EXCLUDED)
               for line in lowered.splitlines())

# instruction.md asserts the cascade runs through both presets and asks the agent
# to say so if a package the notes call affected turns out not to be. Each is
# half the score; naming the removal targets pays nothing, the prompt lists them.
claimed = ["preset-env", "preset-react"]
got = [p for p in claimed if refuted(p)]
score = len(got) / len(claimed)

if not got:
    verdict(0.0,
            "Cites standalone but refutes neither preset: the diamond through "
            "preset-env and preset-react is the claim under test, and the plan "
            "leaves it standing")

verdict(score,
        "Consumer evidenced (standalone); diamond refuted for %d/%d claimed "
        "packages (%s)" % (len(got), len(claimed), ",".join(got)))
'
