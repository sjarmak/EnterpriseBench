#!/usr/bin/env bash
# check_repo_set.sh — checkpoint "identify_repos"
#
# The old check grepped REFACTOR_PLAN.md for 'apimachinery', 'client-go',
# 'apiserver', 'distroless|base.image' and 'k8s.io/api' and scored found/5.
# instruction.md supplies 'distroless' and 'base image', so a
# `cp instruction.md REFACTOR_PLAN.md` copy scored 0.2 here for free.
#
# Worse, all five grep targets were the wrong answer. A Go toolchain bump touches
# NO staging repo: the real PR (#137080) changed seven files and none lives under
# staging/src/. The staging go.mod files declare 'go 1.24.0' before and after —
# that directive is the language version, not the toolchain — and all 31 published
# staging repos take their Go version from one central line,
# staging/publishing/rules.yaml:default-go-version. The propagation set is
# declared by build/dependencies.yaml refPaths, which the old key never named.
# See ground_truth.json:_premise_correction.
#
# The question is precision, not recall: naming the staging repos is what a model
# that knows Kubernetes does without opening anything, and the module edges it
# would cite are REAL — they just carry no constraint for this change. Credit now
# requires 'dependencies.yaml' (ZERO hits in instruction.md) and then pays for
# refuting the cascade, repo by repo (EnterpriseBench-jn73.2.7.3.1.2).
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
            "Propagation set not evidenced: plan never names the manifest that "
            "declares which files a Go bump has to change (%s), so nothing here "
            "shows the checkout was read rather than the prompt restated"
            % (", ".join(missing),))

EXCLUDED = ("not affected", "unaffected", "no change", "no changes", "not require",
            "no work", "out of scope", "not in scope", "excluded", "not impacted",
            "no update", "not need", "does not consume", "not consume",
            "does not depend", "not depend", "no dependency", "does not reference",
            "not reference", "untouched", "not touched", "irrelevant", "no bump",
            "not bumped", "centrally", "central", "no per-repo", "not in the set")

# The refutation must be stated about the repo ON ONE LINE. Scanning the whole
# document would credit a plan that names client-go here and "not affected" in an
# unrelated sentence about something else.
def refuted(repo):
    return any(repo in line and any(term in line for term in EXCLUDED)
               for line in lowered.splitlines())

# instruction.md asserts the bump cascades through the staging repos in
# dependency order and asks the agent to say so if something the notes call
# affected turns out not to be. Each named repo is half the score.
claimed = ["client-go", "apimachinery"]
got = [r for r in claimed if refuted(r)]
score = len(got) / len(claimed)

if not got:
    verdict(0.0,
            "Cites the declaring manifest but refutes no staging repo: the "
            "dependency-ordered staging cascade is the claim under test, and "
            "the plan leaves it standing")

verdict(score,
        "Propagation set evidenced; staging cascade refuted for %d/%d claimed "
        "repos (%s)" % (len(got), len(claimed), ",".join(got)))
'
