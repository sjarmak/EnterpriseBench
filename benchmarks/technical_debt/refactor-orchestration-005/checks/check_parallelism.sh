#!/usr/bin/env bash
# check_parallelism.sh — checkpoint "parallelism"
#
# The old check turned this checkpoint into free credit two ways: it paid 0.4 for
# the bare word 'independent' — which the old prompt handed over verbatim in
# "Parallelization annotations (which removals are independent)" — and 0.2 for
# saying nothing about parallelism at all, so an EMPTY REFACTOR_PLAN.md banked
# 0.06 overall. It also scored the fabricated two-wave answer 0.6 while a correct
# plan got 0.4.
#
# The parallelism answer is downstream of getting the SCOPE and the ordering
# right, so that is what is graded. The four deletions ARE mutually independent,
# but the prompt names all four targets, so "these four are independent of each
# other" is prompt-derivable and pays nothing on its own. What is not derivable
# from the prompt is the constraint that makes the group safe: every one of them
# is referenced by @babel/standalone, so none can be deleted until standalone
# drops its references. A plan that puts standalone inside the parallel group has
# the graph backwards and breaks the build.
#
# 'standalone' has ZERO hits in instruction.md. Absence of work is 0.0
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
import json, os, re

def verdict(score, detail):
    print(json.dumps({"score": round(score, 2), "passed": score >= 0.5, "detail": detail}))
    raise SystemExit(0)

with open(os.environ["GT"]) as fh:
    gt = json.load(fh)

tokens = (gt.get("scoring_evidence") or {}).get("parallelism") or []
if not tokens:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no parallelism evidence in ground_truth.json")

groups = gt.get("parallelizable_steps") or []
if not groups:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no parallelizable_steps in ground_truth.json")
expected = [p.lower() for p in groups[0]]

with open(os.environ["ANSWER"], encoding="utf-8", errors="replace") as fh:
    text = fh.read()
lowered = text.lower()

# Fixed-string containment, never a regex.
missing = [t for t in tokens if t.lower() not in lowered]
if missing:
    verdict(0.0,
            "Scope not evidenced: plan never names the package that references "
            "every removal target (%s), so any claim about what can run in "
            "parallel rests on the asserted diamond rather than these manifests"
            % (", ".join(missing),))

PARALLEL_TERM = re.compile(
    r"parallel|concurrent|independent|simultaneous|same time|together|at once",
    re.IGNORECASE)
HEADING = re.compile(r"^(#{1,6})\s")

# The parallel claim is the section that actually makes it: a heading naming
# parallelism, else a window around each marker line. Scanning the whole document
# would credit a plan that lists the four targets in its ordering section and
# says "parallel" in an unrelated sentence. The window is deliberately generous —
# a correct plan states the group as a sentence plus a bullet list, and the
# ordering constraint behind it ("once standalone lands") is graded by
# check_topo_order, not re-litigated here.
lines = lowered.splitlines()
claim_lines = []

heading_idx = next(
    (i for i, line in enumerate(lines)
     if HEADING.match(line) and PARALLEL_TERM.search(line)), None)
if heading_idx is not None:
    level = len(HEADING.match(lines[heading_idx]).group(1))
    for line in lines[heading_idx + 1:]:
        m = HEADING.match(line)
        if m and len(m.group(1)) <= level:
            break
        claim_lines.append(line)
else:
    for i, line in enumerate(lines):
        if not PARALLEL_TERM.search(line):
            continue
        claim_lines.append(line)
        for follow in lines[i + 1:i + 9]:
            if HEADING.match(follow):
                break
            claim_lines.append(follow)

if not any(line.strip() for line in claim_lines):
    verdict(0.0,
            "Plan states no parallelization claim. The four deletions are "
            "mutually independent once standalone lands; saying nothing is not "
            "a finding and no longer pays")

claim = "\n".join(claim_lines)

EXCLUDED = ("not affected", "unaffected", "no change", "no changes", "not require",
            "no work", "out of scope", "not in scope", "excluded", "not impacted",
            "no update", "not need", "does not consume", "not consume",
            "does not depend", "not depend", "no dependency", "does not reference",
            "not reference", "no second wave", "not a wave")

# There is exactly ONE wave. The old key asserted a second one (preset-react and
# preset-env updated together) and that phantom wave is the signature of a plan
# that believes the prompt: the old check paid 0.6 for it. Scheduling either
# preset into a parallel group is wrong. Naming a preset to rule it out is not,
# hence the same one-line exclusion test check_repo_set.sh uses.
phantom = [p for p in ("preset-env", "preset-react")
           if any(p in line and not any(term in line for term in EXCLUDED)
                  for line in claim_lines)]
if phantom:
    verdict(0.0,
            "Claims a second parallel wave that does not exist (%s): neither "
            "preset depends on any removal target, so no preset work can be "
            "scheduled alongside anything" % (", ".join(phantom),))

named = [p for p in expected if p in claim or p.split("/")[-1] in claim]
recall = len(named) / len(expected)

if not named:
    verdict(0.0,
            "Parallelization claim names none of the four removal targets, so "
            "there is no checkable group")

verdict(recall,
        "Single wave correctly scoped; parallel group covers %d/%d deletions"
        % (len(named), len(expected)))
'
