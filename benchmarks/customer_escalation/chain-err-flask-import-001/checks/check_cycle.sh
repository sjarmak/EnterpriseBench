#!/usr/bin/env bash
# check_cycle.sh — checkpoint "cycle_discrimination"
#
# Grades the per-edge verdict in CYCLE_VERDICT.json against
# ground_truth.json:claimed_edges. Two of the four edges the triage notes claim
# are real and two are invented, so DISCRIMINATION is the signal: which claims
# survive contact with the source.
#
# Negative marking (correct - incorrect) buys exactly one property, and it is the
# one that matters: every BLANKET answer scores 0. "All real" and "all invented"
# are each 2 right and 2 wrong, so "the notes are unconfirmed, so deny everything"
# — the strategy the framing invites — pays nothing. Fraction-correct would have
# handed it 0.5 of the heaviest checkpoint for reading nothing.
#
# What negative marking does NOT buy, contra an earlier draft of this comment:
# random per-edge guessing is NOT worth zero in expectation. The max(0, ...) floor
# is required (a score must land in [0,1]) and it clips losses without capping
# wins, so over the 16 equiprobable guesses E[score] = 0.1875 — 0.075 of the task
# at this weight — and P(all four right) = 1/16. That is the honest number; four
# edges is too few for any per-edge rule to fully suppress guessing. It is
# tolerable because a guesser earns ~0 on the other two checkpoints, which need
# evidence. Recorded in ground_truth.json:_residual_risk (EnterpriseBench-e4w15).
#
# Module identity is normalized (flask.globals / flask/globals.py /
# src/flask/globals.py all denote one module) and unclaimed extra edges are
# ignored, so a correct answer is not failed by spelling or by also reporting the
# real, benign cycles it found.
#
# ground_truth.json is sealed root-only; the agent cannot read the key.
set -euo pipefail

CHECKPOINT="cycle_discrimination"
# Resolve the workspace under all three runners: lib/eb_verify/runner.py passes no
# $1 but sets env + cwd=workspace; scripts/orchestration/milestone.py passes $1 and
# NO env; scripts/sandbox/test_runner.sh passes $1 AND env from a cwd outside the
# workspace. The literal "$WORKSPACE/..." spelling below is also what
# curated_gate_analyzer.DELIV_RE scrapes to find this task's deliverables — spell it
# any other way and the task silently drops out of the suite-wide echo sweep.
WORKSPACE="${1:-${WORKSPACE:-/workspace}}"
VERDICT="$WORKSPACE/flask/CYCLE_VERDICT.json"
# milestone.py sets no env at all, so TASK_DIR must fall back to this script's own
# location (<task_dir>/checks/<this>.sh). In-sandbox the scripts are relocated to
# /workspace/.verifiers/, where that derivation would be wrong — but there
# run_task.py exports TASK_DIR, so the env branch wins.
TASK_DIR="${TASK_DIR:-$(dirname "$(dirname "$(realpath "$0")")")}"
GT="$TASK_DIR/ground_truth.json"
MAX_BYTES=1048576

verdict() { printf '{"score": %s, "passed": %s, "detail": "%s"}\n' "$1" "$2" "$3"; exit 0; }

if [ ! -f "$GT" ]; then
    verdict 0.0 false "VERIFIER_INFRA_ERROR: ground_truth.json not found at $GT"
fi
if [ -L "$VERDICT" ]; then
    verdict 0.0 false "CYCLE_VERDICT.json is a symlink, not a regular file"
fi
if [ ! -f "$VERDICT" ]; then
    verdict 0.0 false "CYCLE_VERDICT.json not found"
fi
if [ "$(wc -c <"$VERDICT")" -gt "$MAX_BYTES" ]; then
    verdict 0.0 false "CYCLE_VERDICT.json exceeds $MAX_BYTES bytes"
fi

export VERDICT GT CHECKPOINT
# python3 -I: isolated mode, so this check does not depend on the caller's env for
# its own integrity. Plain `-c` puts sys.path[0]='' — the cwd — ahead of the stdlib,
# and both Python runners set cwd to the AGENT's workspace, so an agent that drops a
# json.py beside its deliverables would shadow the stdlib and this script's own
# json.dumps would mint whatever verdict the agent wrote (reproduced: a 0.0 came back
# as {"score": 1.0, "detail": "FORGED BY THE AGENT"}). scorer_guard now sets
# PYTHONSAFEPATH=1 for every verifier, which fixes it at the boundary for all callers;
# -I closes it here regardless of who invokes this script. Bead 5cfxa's shadowing
# class, EnterpriseBench-e4w15. -I also implies -E, which drops PYTHON* vars only —
# GT/VERDICT/CHECKPOINT still arrive via os.environ.
python3 -I -c '
import json, os

def out(score, detail):
    print(json.dumps({"score": round(score, 4), "passed": score >= 0.5, "detail": detail}))
    raise SystemExit(0)

def norm(value):
    """flask.globals / flask/globals.py / ./src/flask/globals.py -> flask.globals."""
    s = str(value).strip().lower().replace("\\", "/")
    # "./" first, and repeatedly: it is a natural way to spell a repo-relative path
    # and naive path-joining produces "././x". Leaving it in made a CORRECT answer
    # normalize to "..src.flask.globals" and silently miss the key on the
    # heaviest-weighted checkpoint — failing the answer for its spelling, which is
    # the one thing this normalization exists to prevent.
    while s.startswith("./"):
        s = s[2:]
    if s.startswith("src/"):
        s = s[4:]
    if s.endswith("/__init__.py"):
        s = s[: -len("/__init__.py")]
    elif s.endswith(".py"):
        s = s[:-3]
    s = s.strip("/").replace("/", ".")
    if s.endswith(".__init__"):
        s = s[: -len(".__init__")]
    return s

# The answer key gets the same never-raise discipline as the agent file below: a
# corrupt or hand-edited ground_truth.json must surface as VERIFIER_INFRA_ERROR, not
# as a bare traceback with no verdict on stdout.
try:
    with open(os.environ["GT"]) as fh:
        key = {
            (norm(e["from"]), norm(e["to"])): bool(e["imported_at_runtime"])
            for e in json.load(fh)["claimed_edges"]
        }
except (ValueError, KeyError, TypeError, OSError) as exc:
    out(0.0, "VERIFIER_INFRA_ERROR: unreadable claimed_edges in ground_truth.json: %s"
        % type(exc).__name__)
if not key:
    out(0.0, "VERIFIER_INFRA_ERROR: ground_truth.json has no claimed_edges")

try:
    with open(os.environ["VERDICT"], encoding="utf-8") as fh:
        data = json.load(fh)
except (json.JSONDecodeError, UnicodeDecodeError) as exc:
    out(0.0, "CYCLE_VERDICT.json is not valid JSON: %s" % exc)

if not isinstance(data, dict) or not isinstance(data.get("claimed_edges"), list):
    out(0.0, "CYCLE_VERDICT.json has no claimed_edges list")

# Extra edges the agent reports are simply not graded; last write wins per edge.
answered = {}
for entry in data["claimed_edges"]:
    if not isinstance(entry, dict):
        continue
    try:
        edge = (norm(entry["from"]), norm(entry["to"]))
    except KeyError:
        continue
    flag = entry.get("imported_at_runtime")
    if edge in key and isinstance(flag, bool):
        answered[edge] = flag

correct = sum(1 for e, want in key.items() if answered.get(e) is want)
incorrect = len(key) - correct   # a wrong verdict and a missing one both cost
score = max(0.0, (correct - incorrect) / len(key))
out(score, "%d/%d claimed edges classified correctly for %s"
    % (correct, len(key), os.environ["CHECKPOINT"]))
'
