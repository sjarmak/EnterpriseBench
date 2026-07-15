#!/usr/bin/env bash
# check_transitive_paths.sh — checkpoint "trace_transitive_paths"
#
# Credits ONLY evidence the prompt does not already contain
# (EnterpriseBench-vjrbw). The task's instruction.md hands the agent the CVE id,
# the consumer repo names, and the fixed version, so grepping the report for
# those tokens scored a verbatim copy of the prompt at 1.00. Instead we grade
# against ground_truth.json:scoring_evidence[<checkpoint>] — tokens that are (a)
# absent from instruction.md and (b) present in expected_solution.json, so they
# are reachable only by an agent that actually researched the advisory / read the
# manifests, never by echoing the prompt. ground_truth.json is sealed root-only
# (run_task.py GRADING_PATHS), so its tokens cannot leak to the agent.
set -euo pipefail

CHECKPOINT="trace_transitive_paths"
WORKSPACE="${WORKSPACE:-/workspace}"
REPORT="$WORKSPACE/BLAST_RADIUS.md"
GT="${TASK_DIR:-}/ground_truth.json"
MAX_REPORT_BYTES=1048576

verdict() { printf '{"score": %s, "passed": %s, "reason": "%s"}\n' "$1" "$2" "$3"; exit 0; }

# The answer key is ours: a missing ground_truth means the verifier did not
# really run — route to re-run rather than bury it under an agent 0.0.
if [[ ! -f "$GT" ]]; then
  verdict 0.0 false "VERIFIER_INFRA_ERROR: ground_truth.json not found at $GT"
fi
# BLAST_RADIUS.md is agent-owned; refuse a symlink rather than read its target.
if [[ -L "$REPORT" ]]; then
  verdict 0.0 false "BLAST_RADIUS.md is a symlink, not a regular file"
fi
if [[ ! -f "$REPORT" ]]; then
  verdict 0.0 false "BLAST_RADIUS.md not found"
fi
if [[ "$(wc -c <"$REPORT")" -gt "$MAX_REPORT_BYTES" ]]; then
  verdict 0.0 false "BLAST_RADIUS.md exceeds ${MAX_REPORT_BYTES} bytes"
fi

export REPORT GT CHECKPOINT
python3 -c '
import json, os, re

def verdict(score, detail):
    print(json.dumps({"score": round(score, 2), "passed": score >= 0.5, "reason": detail}))
    raise SystemExit(0)

with open(os.environ["GT"]) as fh:
    gt = json.load(fh)
evidence = (gt.get("scoring_evidence") or {}).get(os.environ["CHECKPOINT"]) or []
if not evidence:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no scoring_evidence for " + os.environ["CHECKPOINT"])

with open(os.environ["REPORT"], encoding="utf-8", errors="replace") as fh:
    text = fh.read().lower()

def present(token):
    tok = token.lower()
    if re.fullmatch(r"v?\d+(\.\d+)+", tok):
        # A version: boundary-match so 2.0 does not hit inside 2.0.5 / 12.0, yet a
        # trailing sentence period (1.58.3.) still counts as the bare version.
        return re.search(r"(?<![\d.])" + re.escape(tok) + r"(?!\d)(?!\.\d)", text) is not None
    return tok in text

found = sum(1 for token in evidence if present(token))
verdict(found / len(evidence),
        "Cited %d/%d non-prompt evidence tokens for %s" % (found, len(evidence), os.environ["CHECKPOINT"]))
'
