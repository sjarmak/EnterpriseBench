#!/usr/bin/env bash
# check_policy_types.sh — checkpoint "identify_policy_types"
#
# Credits ONLY evidence the prompt does not already contain
# (EnterpriseBench-jn73.2.7.3).
#
# The old check grepped the report for the four policy-type names,
# which nest inside each other (NetworkPolicy < GlobalNetworkPolicy <
# StagedGlobalNetworkPolicy), so naming one type scored two.
#
# Instead we grade against ground_truth.json:scoring_evidence[<checkpoint>] —
# tokens that are (a) absent from every prompt variant this task ships and (b)
# present in expected_solution.json, so they are reachable only by an agent that
# actually read the code, never by echoing the prompt. ground_truth.json is
# sealed root-only (run_task.py GRADING_PATHS), so its tokens cannot leak.
set -euo pipefail

CHECKPOINT="identify_policy_types"
WORKSPACE="${WORKSPACE:-/workspace}"
REPORT="$WORKSPACE/security_audit.md"
GT="${TASK_DIR:-}/ground_truth.json"
MAX_REPORT_BYTES=1048576

# The sentinel rides in `detail`: scorer_guard scans that field and no other, so
# a sentinel under any other key is invisible and lands as a real agent 0.0.
verdict() { printf '{"score": %s, "passed": %s, "detail": "%s"}\n' "$1" "$2" "$3"; exit 0; }

# The answer key is ours: a missing ground_truth means the verifier did not
# really run — route to re-run rather than bury it under an agent 0.0.
if [[ ! -f "$GT" ]]; then
  verdict 0.0 false "VERIFIER_INFRA_ERROR: ground_truth.json not found at $GT"
fi
# security_audit.md is agent-owned; refuse a symlink rather than read its target.
if [[ -L "$REPORT" ]]; then
  verdict 0.0 false "security_audit.md is a symlink, not a regular file"
fi
if [[ ! -f "$REPORT" ]]; then
  verdict 0.0 false "security_audit.md not found"
fi
if [[ "$(wc -c <"$REPORT")" -gt "$MAX_REPORT_BYTES" ]]; then
  verdict 0.0 false "security_audit.md exceeds ${MAX_REPORT_BYTES} bytes"
fi

export REPORT GT CHECKPOINT
python3 -c '
import json, os

def verdict(score, detail):
    print(json.dumps({"score": round(score, 2), "passed": score >= 0.5, "detail": detail}))
    raise SystemExit(0)

with open(os.environ["GT"]) as fh:
    gt = json.load(fh)
evidence = (gt.get("scoring_evidence") or {}).get(os.environ["CHECKPOINT"]) or []
if not evidence:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no scoring_evidence for " + os.environ["CHECKPOINT"])

with open(os.environ["REPORT"], encoding="utf-8", errors="replace") as fh:
    text = fh.read().lower()

# Plain substring, no version-boundary branch: none of this task family grades on
# a bare version, and test_heterogeneous_prompt_echo pins that so a version token
# added later fails loudly here instead of silently matching inside a longer one.
found = sum(1 for token in evidence if token.lower() in text)
verdict(found / len(evidence),
        "Cited %d/%d non-prompt evidence tokens for %s" % (found, len(evidence), os.environ["CHECKPOINT"]))
'
