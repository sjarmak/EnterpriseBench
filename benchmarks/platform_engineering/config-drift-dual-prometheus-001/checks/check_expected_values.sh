#!/usr/bin/env bash
# check_expected_values.sh — checkpoint "expected_values"
#
# Grades DRIFT_REPORT.json against
# ground_truth.json:scoring_evidence[drift_mechanism] (sealed root-only). The
# previous file was a byte-identical copy of the bitnami/consul task's verifier
# and looked for 'serflan' in field names this schema does not define; it is
# replaced, not patched.
#
# The whole task turns on one fact the prompt cannot give away: Prometheus's
# max-block-duration has NO declared default. It is computed at startup from
# retention — cmd/prometheus/main.go:553-563, `maxBlockDuration = retention / 10`
# with the default retention of 15d (defaultRetentionString, main.go:93) — so it
# lands on 36h against a min of 2h, and the Thanos sidecar refuses to start.
#
# So the graded anchors are "15d" and "cmd/prometheus/main.go": the value the
# arithmetic runs on, and the file it runs in. Both score 0 against
# instruction.md, which names the flags but never the computation. An agent that
# only read tsdb/db.go sees Min == Max == 2h and reports no drift; an agent that
# only read the prompt can name the flags but cannot say where 36h comes from.
# Each token is scored on its own (found/len), so both must be non-prompt.
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
REPORT="$WORKSPACE/DRIFT_REPORT.json"
GT="${TASK_DIR:-}/ground_truth.json"
MAX_REPORT_BYTES=1048576

verdict() { printf '{"score": %s, "passed": %s, "detail": "%s"}\n' "$1" "$2" "$3"; exit 0; }

if [[ ! -f "$GT" ]]; then
  verdict 0.0 false "VERIFIER_INFRA_ERROR: ground_truth.json not found at $GT"
fi
if [[ -L "$REPORT" ]]; then
  verdict 0.0 false "DRIFT_REPORT.json is a symlink, not a regular file"
fi
if [[ ! -f "$REPORT" ]]; then
  verdict 0.0 false "DRIFT_REPORT.json not found"
fi
if [[ "$(wc -c <"$REPORT")" -gt "$MAX_REPORT_BYTES" ]]; then
  verdict 0.0 false "DRIFT_REPORT.json exceeds ${MAX_REPORT_BYTES} bytes"
fi

export REPORT GT
python3 -c '
import json, os, re

def verdict(score, detail):
    print(json.dumps({"score": round(score, 2), "passed": score >= 0.5, "detail": detail}))
    raise SystemExit(0)

with open(os.environ["GT"]) as fh:
    evidence = (json.load(fh).get("scoring_evidence") or {}).get("drift_mechanism") or []
if not evidence:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no scoring_evidence[drift_mechanism] in ground_truth.json")

try:
    with open(os.environ["REPORT"], encoding="utf-8", errors="replace") as fh:
        report = json.load(fh)
except (json.JSONDecodeError, UnicodeDecodeError) as exc:
    verdict(0.0, "DRIFT_REPORT.json is not valid JSON: " + str(exc))
if not isinstance(report, dict):
    verdict(0.0, "DRIFT_REPORT.json is not a JSON object")

# The mechanism may land in prometheus_default, override_chain or a summary;
# grade the claim, not the field it went in.
haystack = re.sub(r"\s+", "", json.dumps(report)).lower()
found = [t for t in evidence if re.sub(r"\s+", "", t).lower() in haystack]

verdict(len(found) / len(evidence),
        "Traced %d/%d source-only anchors of the computed default (%s)"
        % (len(found), len(evidence), ", ".join(found) if found else "none"))
'
