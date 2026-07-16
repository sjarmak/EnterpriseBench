#!/usr/bin/env bash
# check_drift_points.sh — checkpoint "drift_points"
#
# Grades DRIFT_REPORT.json against ground_truth.json:drift_points (sealed
# root-only), rebuilt by sweeping argo-cd v2.9.0 flag/constant defaults against
# argo-helm argo-cd-5.51.0 values.yaml.
#
# This file previously WAS config-drift-001's verifier, byte for byte: it graded
# serflan/serfwan Helm port drift for a bitnami/consul chart this task does not
# clone, read $WORKSPACE/charts/DRIFT_REPORT.json when the instruction says
# /workspace/DRIFT_REPORT.json, and matched field names (file/key/expected) that
# this task's schema does not define. A perfect answer scored 0.0 — the task was
# un-passable for its whole life, which tests/test_task_output_path_consistency.py
# has been failing on.
#
# Precision is graded alongside recall because the task's original premise was
# false. instruction.md used to ask for drift "around sync timeouts, retry
# settings"; every one of those knobs matches (app-resync 180, status-processors
# 20, operation-processors 10, self-heal 5, repo-server timeout 60). An agent
# that "finds" drift there is fabricating to satisfy the prompt — the exact
# failure this family suffered from. ground_truth:not_drifted names them.
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
    gt = json.load(fh)
expected = gt.get("drift_points") or []
if not expected:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no drift_points in ground_truth.json")

try:
    with open(os.environ["REPORT"], encoding="utf-8", errors="replace") as fh:
        report = json.load(fh)
except (json.JSONDecodeError, UnicodeDecodeError) as exc:
    verdict(0.0, "DRIFT_REPORT.json is not valid JSON: " + str(exc))
if not isinstance(report, dict):
    verdict(0.0, "DRIFT_REPORT.json is not a JSON object")

claimed = report.get("drift_points")
if not isinstance(claimed, list) or not claimed:
    verdict(0.0, "DRIFT_REPORT.json has no drift_points array")

def norm(value):
    return re.sub(r"\s+", "", json.dumps(value) if not isinstance(value, str) else value).lower()

found, detail = 0, []
for want in expected:
    ident = [t.lower() for t in (want.get("evidence_tokens") or {}).get("identifies", [])]
    hit = any(
        isinstance(p, dict) and all(t in norm(p.get("config_key", "")) for t in ident)
        for p in claimed
    )
    found += hit
    detail.append(str(want.get("config_key")) + ("=hit" if hit else "=miss"))

# A fabricated drift point is worse than a missed one here: a fabricated key is
# what made this task un-passable in the first place.
fabricated = []
for entry in gt.get("not_drifted") or []:
    if "literal" in str(entry.get("note", "")).lower():
        continue  # applicationsetcontroller.policy is a real literal difference
    for token in ("resync", "processors", "self-heal", "self.heal", "timeout"):
        if any(isinstance(p, dict) and token in norm(p.get("config_key", "")) for p in claimed):
            fabricated.append(token)

score = found / len(expected)
if fabricated:
    score *= 0.5
    detail.append("penalised for drift that does not exist at these revs: " + ", ".join(sorted(set(fabricated))))

verdict(score, "Found %d/%d real drift points: %s" % (found, len(expected), ", ".join(detail)))
'
