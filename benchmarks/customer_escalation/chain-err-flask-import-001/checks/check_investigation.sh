#!/usr/bin/env bash
# check_investigation.sh — checkpoint "investigation_evidence"
#
# Re-anchored to ground_truth.json:scoring_evidence[investigation_evidence]
# (EnterpriseBench-e4w15). This check used to grep "circular import" and "module"
# — concept vocabulary the session prompt stated verbatim — so a copy of the prompt
# scored 1.0. It now credits ONLY evidence a reader of src/flask/globals.py has and
# no prompt supplies: the TYPE_CHECKING guard that makes the claimed
# flask.globals -> flask.app edge a type-checker-only import, and the werkzeug
# LocalProxy / ContextVar machinery that is what globals.py actually imports at
# runtime. An echo of the prompt cites none of them and scores 0.
#
# The tokens are flat strings scored one-for-one, which is what
# tests/integrity/test_scoring_evidence_is_nonprompt.py can read and assert are
# absent from the prompt. A nested any-of shape would be silently skipped by that
# invariant (it only walks `isinstance(t, str)`), trading brittleness for a blind
# spot. Each token is instead chosen to survive lowercased substring matching:
# "type_checking" matches TYPE_CHECKING, "contextvar" matches both ContextVar and
# contextvars, "werkzeug" matches werkzeug.local.
#
# ground_truth.json is sealed root-only; the agent cannot read the key.
set -euo pipefail

CHECKPOINT="investigation_evidence"
# See check_cycle.sh for why the workspace and TASK_DIR are resolved this way (three
# runners, three conventions) and why the literal "$WORKSPACE/..." spelling matters.
WORKSPACE="${1:-${WORKSPACE:-/workspace}}"
REPORT="$WORKSPACE/flask/INVESTIGATION.md"
TASK_DIR="${TASK_DIR:-$(dirname "$(dirname "$(realpath "$0")")")}"
GT="$TASK_DIR/ground_truth.json"
MAX_BYTES=1048576

verdict() { printf '{"score": %s, "passed": %s, "detail": "%s"}\n' "$1" "$2" "$3"; exit 0; }

if [ ! -f "$GT" ]; then
    verdict 0.0 false "VERIFIER_INFRA_ERROR: ground_truth.json not found at $GT"
fi
if [ -L "$REPORT" ]; then
    verdict 0.0 false "INVESTIGATION.md is a symlink, not a regular file"
fi
if [ ! -f "$REPORT" ]; then
    verdict 0.0 false "INVESTIGATION.md not found"
fi
if [ "$(wc -c <"$REPORT")" -gt "$MAX_BYTES" ]; then
    verdict 0.0 false "INVESTIGATION.md exceeds $MAX_BYTES bytes"
fi

export REPORT GT CHECKPOINT
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

evidence = (gt.get("scoring_evidence") or {}).get(os.environ["CHECKPOINT"]) or []
if not evidence:
    out(0.0, "VERIFIER_INFRA_ERROR: no scoring_evidence for " + os.environ["CHECKPOINT"])

with open(os.environ["REPORT"], encoding="utf-8", errors="replace") as fh:
    text = fh.read().lower()

found = sum(1 for token in evidence if token.lower() in text)
out(found / len(evidence),
    "Cited %d/%d non-prompt evidence tokens for %s"
    % (found, len(evidence), os.environ["CHECKPOINT"]))
'
