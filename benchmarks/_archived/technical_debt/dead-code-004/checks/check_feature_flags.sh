#!/usr/bin/env bash
# check_feature_flags.sh — For TypeScript, no feature flags to check.
# Score based on breadth: agent must find dead code in ≥5 files.
# Env: WORKSPACE, TASK_DIR, TASK_ID
set -euo pipefail

REPORT="${WORKSPACE}/TypeScript/dead_code_report.json"

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

# Count unique files with dead code claims
files = {item["file"] for item in claimed if item.get("file")}
file_count = len(files)

# Target: 5+ files for full score
if file_count >= 5:
    score = 1.0
elif file_count >= 3:
    score = 0.6
elif file_count >= 1:
    score = 0.3
else:
    score = 0.0

detail = f"unique_files={file_count} (target≥5)"
print(json.dumps({"score": round(score, 4), "detail": detail}))
PYEOF
