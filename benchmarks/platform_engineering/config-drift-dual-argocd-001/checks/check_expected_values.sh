#!/usr/bin/env bash
# check_expected_values.sh — checkpoint "expected_values"
#
# Grades DRIFT_REPORT.json against ground_truth.json:drift_points (sealed
# root-only). The previous file was a byte-identical copy of the bitnami/consul
# task's verifier and looked for 'serflan' in field names this schema does not
# define; it is replaced, not patched.
#
# A drift claim is only worth anything with BOTH sides of it, so both are graded
# per drift point: the argo-cd compiled-in default and the argo-helm override.
# Neither is reachable from the prompt — instruction.md names no file, no flag
# and no label value, and both label strings score 0 against it. Knowing that
# argo-cd defaults to app.kubernetes.io/instance means having read
# common/common.go:149 (and settings.go, to know the constant is the fallback
# when the ConfigMap key is empty); knowing the chart ships
# argocd.argoproj.io/instance means having read values.yaml:165.
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
    expected = json.load(fh).get("drift_points") or []
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

earned = 0.0
detail = []
for want in expected:
    tokens = want.get("evidence_tokens") or {}
    ident = [t.lower() for t in tokens.get("identifies", [])]
    want_default = [t.lower() for t in tokens.get("default", [])]
    want_override = [t.lower() for t in tokens.get("override", [])]

    point = next(
        (p for p in claimed
         if isinstance(p, dict) and all(t in norm(p.get("config_key", "")) for t in ident)),
        None,
    )
    if point is None:
        detail.append(str(want.get("config_key")) + "=not-reported")
        continue

    # Accept the values wherever the agent put them: the schema has dedicated
    # argocd_default / helm_override fields, but grade the claim, not the field.
    blob = norm(point)
    got_default = all(t in blob for t in want_default)
    got_override = all(t in blob for t in want_override)
    earned += (0.5 * got_default) + (0.5 * got_override)
    detail.append("%s=default:%s,override:%s"
                  % (want.get("config_key"), "hit" if got_default else "miss",
                     "hit" if got_override else "miss"))

verdict(earned / len(expected),
        "Both sides cited for %.1f/%d drift points: %s" % (earned, len(expected), ", ".join(detail)))
'
