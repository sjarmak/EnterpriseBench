#!/usr/bin/env bash
# check_resolution.sh — checkpoint "resolution_correct"
#
# Grades the DECISION, not a diff. This was check_fix.sh, which awarded its full
# weight for (a) a FIX_SUMMARY.md over 50 bytes and (b) any *.py file showing up in
# the workspace repo's diff against HEAD~1 — bare changed-file membership. It could
# not tell a fix from a comment because it never read the code's meaning, so one
# comment appended to tests/conftest.py paid 0.40 (EnterpriseBench-uc12m / -e4w15).
#
# The correct resolution is that NO code change is warranted: the reported cycle
# does not exist, so there is nothing to break, and patching working code to defer
# an import that is already absent would add risk and fix nothing. Because the
# decision is the deliverable, no diff is graded at all — that is what removes the
# comment vector, rather than tightening a match that was never measuring the fix.
#
# The decision GATES the evidence rather than scoring beside it: a wrong decision is
# 0 outright, and a right one earns only what its reason can evidence. So guessing
# "no change" — which the escalation pressure in session 2 invites — pays nothing on
# its own.
#
# ground_truth.json is sealed root-only; the agent cannot read the key.
set -euo pipefail

CHECKPOINT="resolution_correct"
# See check_cycle.sh for why the workspace and TASK_DIR are resolved this way (three
# runners, three conventions) and why the literal "$WORKSPACE/..." spelling matters.
WORKSPACE="${1:-${WORKSPACE:-/workspace}}"
RESOLUTION="$WORKSPACE/flask/RESOLUTION.json"
TASK_DIR="${TASK_DIR:-$(dirname "$(dirname "$(realpath "$0")")")}"
GT="$TASK_DIR/ground_truth.json"
MAX_BYTES=1048576

verdict() { printf '{"score": %s, "passed": %s, "detail": "%s"}\n' "$1" "$2" "$3"; exit 0; }

if [ ! -f "$GT" ]; then
    verdict 0.0 false "VERIFIER_INFRA_ERROR: ground_truth.json not found at $GT"
fi
if [ -L "$RESOLUTION" ]; then
    verdict 0.0 false "RESOLUTION.json is a symlink, not a regular file"
fi
if [ ! -f "$RESOLUTION" ]; then
    verdict 0.0 false "RESOLUTION.json not found"
fi
if [ "$(wc -c <"$RESOLUTION")" -gt "$MAX_BYTES" ]; then
    verdict 0.0 false "RESOLUTION.json exceeds $MAX_BYTES bytes"
fi

export RESOLUTION GT CHECKPOINT
# See check_cycle.sh for why this is `python3 -I` and not `python3` (an agent's
# json.py beside its deliverables would otherwise shadow the stdlib and mint this
# script's verdict). -I implies -E, which drops PYTHON* vars only: the exports
# above still arrive via os.environ.
python3 -I -c '
import json, os

def out(score, detail):
    print(json.dumps({"score": round(score, 4), "passed": score >= 0.5, "detail": detail}))
    raise SystemExit(0)

try:
    with open(os.environ["GT"]) as fh:
        gt = json.load(fh)
except (ValueError, OSError) as exc:
    out(0.0, "VERIFIER_INFRA_ERROR: unreadable ground_truth.json: %s" % type(exc).__name__)
if not isinstance(gt, dict):
    out(0.0, "VERIFIER_INFRA_ERROR: ground_truth.json is not an object")

expected = gt.get("code_change_required")
evidence = (gt.get("scoring_evidence") or {}).get(os.environ["CHECKPOINT"]) or []
if not isinstance(expected, bool) or not evidence:
    out(0.0, "VERIFIER_INFRA_ERROR: ground_truth lacks code_change_required/scoring_evidence")

try:
    with open(os.environ["RESOLUTION"], encoding="utf-8") as fh:
        data = json.load(fh)
except (json.JSONDecodeError, UnicodeDecodeError) as exc:
    out(0.0, "RESOLUTION.json is not valid JSON: %s" % exc)

if not isinstance(data, dict):
    out(0.0, "RESOLUTION.json is not a JSON object")

decision = data.get("code_change_required")
if not isinstance(decision, bool):
    out(0.0, "RESOLUTION.json has no boolean code_change_required")
if decision is not expected:
    out(0.0, "Wrong resolution: code_change_required=%s" % decision)

reason = data.get("reason")
if not isinstance(reason, str):
    out(0.0, "Right decision but no reason string to evidence it")
text = reason.lower()

found = sum(1 for token in evidence if token.lower() in text)
out(found / len(evidence),
    "Correct decision; reason cited %d/%d non-prompt evidence tokens"
    % (found, len(evidence)))
'
