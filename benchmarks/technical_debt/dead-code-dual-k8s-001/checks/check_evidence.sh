#!/usr/bin/env bash
# check_evidence.sh — Validate that each dead code claim has evidence.
# Checks: (a) every entry has non-empty evidence, (b) evidence mentions callers/references.
# Env: WORKSPACE, TASK_DIR, TASK_ID
set -euo pipefail

REPORT="${WORKSPACE}/react/dead_code_report.json"

if [[ ! -f "$REPORT" ]]; then
    echo '{"score": 0.0, "detail": "No dead_code_report.json found"}'
    exit 0
fi

python3 - "$REPORT" <<'PYEOF'
import json
import sys

report_path = sys.argv[1]

with open(report_path) as f:
    claimed = json.load(f)

if not claimed:
    print(json.dumps({"score": 0.0, "detail": "Empty report"}))
    sys.exit(0)

# Evidence quality keywords
QUALITY_KEYWORDS = [
    "never called", "no callers", "zero callers", "no references",
    "zero references", "unused", "not imported", "no importers",
    "dead", "unreachable", "removed", "deprecated", "permanently",
    "always", "never", "no longer"
]

has_evidence_count = 0
quality_evidence_count = 0

for item in claimed:
    evidence = item.get("evidence", "").strip()
    if evidence:
        has_evidence_count += 1
        evidence_lower = evidence.lower()
        if any(kw in evidence_lower for kw in QUALITY_KEYWORDS):
            quality_evidence_count += 1

total = len(claimed)
evidence_ratio = has_evidence_count / total
quality_ratio = quality_evidence_count / total

# Score: 60% for having evidence, 40% for quality evidence
score = 0.6 * evidence_ratio + 0.4 * quality_ratio

detail = (
    f"entries={total} has_evidence={has_evidence_count} "
    f"quality_evidence={quality_evidence_count}"
)
print(json.dumps({"score": round(score, 4), "detail": detail}))
PYEOF
