#!/usr/bin/env bash
# check_parallelism.sh — checkpoint "parallelism"
#
# This check was inverted: it paid the wrong answer and docked the right one.
#
# ground_truth.parallelizable_steps was [], so the check took the "no parallel
# steps" branch and awarded 1.0 for the words 'sequential'/'serial'/'depends on'
# and 0.3 for mentioning parallelism at all. But [] was itself wrong: it follows
# from the fabricated tokio -> hyper -> axum chain. At the pinned revisions hyper
# and axum both depend on tokio DIRECTLY and neither depends on the other (axum
# 0.6.19 wants hyper ^0.14.24; the workspace vendors 1.0.0-rc.4), so they are
# parallelizable. The old prompt called the chain "strict", so an agent echoing
# it wrote "sequential" and scored 1.0, while an agent that read the manifests
# and correctly reported hyper || axum scored 0.3.
#
# It also paid 0.5 for silence: a plan that never mentioned parallelism at all
# — including an EMPTY file — took the "did not explicitly address" branch and
# banked 0.5 of this checkpoint's 0.30. Absence of work is now 0.0.
#
# Credit now requires naming the concurrent pair (hyper and axum together on one
# line, with a parallelism term) AND citing the manifest fact that establishes
# their independence (axum's hyper requirement, 0.14.x — ZERO hits in
# instruction.md). Claiming "hyper || axum" without that evidence is a coin flip
# between the two shapes, not a finding (EnterpriseBench-jn73.2.7.3.1.2).
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
import json, os, re

def verdict(score, detail):
    print(json.dumps({"score": round(score, 2), "passed": score >= 0.5, "detail": detail}))
    raise SystemExit(0)

with open(os.environ["GT"]) as fh:
    gt = json.load(fh)

groups = gt.get("parallelizable_steps") or []
if not groups:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no parallelizable_steps in ground_truth.json")

tokens = (gt.get("scoring_evidence") or {}).get("parallelism") or []
if not tokens:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no parallelism evidence in ground_truth.json")

with open(os.environ["ANSWER"], encoding="utf-8", errors="replace") as fh:
    text = fh.read()
lowered = text.lower()

PARALLEL = ("parallel", "concurrent", "simultaneous", "at the same time",
            "independent", "independently")

def last_segment(name):
    return name.rstrip("/").split("/")[-1].strip().lower()

# A group is claimed when ONE line ties its members together with a parallelism
# term. Scanning the whole document instead would credit a plan that says
# "hyper" here, "axum" there and "parallel" in an unrelated sentence.
hits, detail = 0, []
for group in groups:
    members = [last_segment(m) for m in group]
    claimed = any(
        any(term in line for term in PARALLEL) and all(m in line for m in members)
        for line in lowered.splitlines()
    )
    hits += claimed
    detail.append("+".join(members) + ("=hit" if claimed else "=miss"))

# Fixed-string containment, never a regex: "." in "0.14" would match "0x14".
missing = [t for t in tokens if t.lower() not in lowered]
if missing:
    verdict(0.0,
            "Parallel pair not evidenced: plan never cites the hyper requirement "
            "axum declares (%s), so any claim that hyper and axum are independent "
            "is unsupported by these manifests (%s)"
            % (", ".join(missing), ", ".join(detail)))

verdict(hits / len(groups),
        "Identified %d/%d parallelizable groups with manifest evidence: %s"
        % (hits, len(groups), ", ".join(detail)))
'
