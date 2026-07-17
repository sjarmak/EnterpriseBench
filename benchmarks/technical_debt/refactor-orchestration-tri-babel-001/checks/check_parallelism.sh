#!/usr/bin/env bash
# check_parallelism.sh — checkpoint "parallelism"
#
# ground_truth.parallelizable_steps is [] and stays [], but the old check turned
# that into free credit two ways: it paid 1.0 for the words 'sequential' /
# 'serial' / 'depends on' — which the old prompt's "strict dependency chain"
# handed the agent outright — and 0.5 for saying nothing about parallelism at
# all, so an EMPTY REFACTOR_PLAN.md banked half of this checkpoint's 0.30.
#
# The [] was also right for the wrong reason: it followed from the fabricated
# babel -> webpack -> next.js chain. There is nothing to parallelize because
# webpack needs no work at all (it parses with acorn ^8.7.1, not Babel), leaving
# two repos in a strict order. The parallelism answer is downstream of getting
# the SCOPE right, so that is what is graded: the plan must exclude webpack
# explicitly and cite what it actually parses with.
#
# 'acorn' has ZERO hits in instruction.md. Absence of work is 0.0
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

tokens = (gt.get("scoring_evidence") or {}).get("parallelism") or []
if not tokens:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no parallelism evidence in ground_truth.json")

with open(os.environ["ANSWER"], encoding="utf-8", errors="replace") as fh:
    text = fh.read()
lowered = text.lower()

# Fixed-string containment, never a regex.
missing = [t for t in tokens if t.lower() not in lowered]
if missing:
    verdict(0.0,
            "Scope not evidenced: plan never names what webpack actually parses "
            "with (%s), so any claim about what can run in parallel rests on the "
            "assumed chain rather than these manifests" % (", ".join(missing),))

EXCLUDED = ("not affected", "unaffected", "no change", "no changes", "not require",
            "no work", "out of scope", "not in scope", "excluded", "not impacted",
            "no update", "not need", "does not consume", "not consume",
            "does not parse", "not parse")

# The finding must be stated about webpack ON ONE LINE. Scanning the whole
# document would credit a plan that says "webpack" here and "not affected" in an
# unrelated sentence about something else.
excluded_webpack = any(
    "webpack" in line and any(term in line for term in EXCLUDED)
    for line in lowered.splitlines()
)
if not excluded_webpack:
    verdict(0.0,
            "Plan cites acorn but never states webpack is out of scope for this "
            "change, so it has not drawn the conclusion the evidence forces")

verdict(1.0,
        "Correctly scopes webpack out (evidenced by acorn), leaving babel -> "
        "next.js strictly ordered with no parallelizable steps")
'
