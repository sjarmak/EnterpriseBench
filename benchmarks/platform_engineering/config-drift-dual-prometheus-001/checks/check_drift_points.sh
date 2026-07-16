#!/usr/bin/env bash
# check_drift_points.sh — checkpoint "drift_points"
#
# Grades DRIFT_REPORT.json against ground_truth.json:drift_points (sealed
# root-only), authored from source at prometheus v2.48.0 / thanos v0.32.5.
#
# This file previously WAS config-drift-001's verifier, byte for byte: it graded
# serflan/serfwan Helm port drift for a bitnami/consul chart this task does not
# clone, read $WORKSPACE/charts/DRIFT_REPORT.json when the instruction says
# /workspace/DRIFT_REPORT.json, and matched field names (file/key/expected) this
# schema does not define. A perfect answer scored 0.0.
#
# The prompt lists "min-block-duration, max-block-duration, retention policies,
# and external label requirements" outright, so naming a drifting key proves
# nothing — it is reading the prompt back. What cannot be reached from the prompt
# is the ARITHMETIC: max-block-duration has no declared default, and
# cmd/prometheus/main.go computes it as retention/10 = 15d/10 = 36h at startup,
# against a min of 2h. Every one of "15d", "36h", "31d" and the file path scores
# 0 against instruction.md. That is why each drift point must pair its key with
# the computation and the Thanos-side file.
#
# tsdb/db.go is the trap the ground_truth's not_drifted records: DefaultOptions
# sets Min == Max == 2h, which AGREES with Thanos. A report blaming the TSDB
# defaults has traced the wrong layer, which is exactly what the required_files
# weighting used to steer an agent toward.
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

found, detail = 0, []
for want in expected:
    tokens = want.get("evidence_tokens") or {}
    ident = [t.lower() for t in tokens.get("identifies", [])]
    computation = [t.lower() for t in tokens.get("computation", [])]
    thanos_side = [t.lower() for t in tokens.get("thanos_side", [])]
    hit = False
    for point in claimed:
        if not isinstance(point, dict):
            continue
        if not all(t in norm(point.get("config_key", "")) for t in ident):
            continue
        # The key alone is prompt vocabulary. Credit needs the source-only
        # arithmetic AND the Thanos side of the comparison, looked for anywhere
        # in the point: agents spread these across default/expectation/chain.
        blob = norm(point)
        if all(t in blob for t in computation) and all(t in blob for t in thanos_side):
            hit = True
            break
    found += hit
    detail.append(str(want.get("config_key")) + ("=hit" if hit else "=miss"))

verdict(found / len(expected),
        "Identified %d/%d drift points with both the source-only computation and the Thanos side: %s"
        % (found, len(expected), ", ".join(detail)))
'
