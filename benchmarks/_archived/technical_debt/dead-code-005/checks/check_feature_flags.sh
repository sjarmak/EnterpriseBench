#!/usr/bin/env bash
# check_feature_flags.sh — For Angular, check breadth of dead file identification.
# Agent must find ≥8 dead files for full score.
# Env: WORKSPACE, TASK_DIR, TASK_ID
set -euo pipefail

REPORT="${WORKSPACE}/angular/dead_code_report.json"

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

# Count file-level dead code claims
dead_files = {item["file"] for item in claimed
              if item.get("kind") == "file" or item.get("symbol") == "default"}
file_count = len(dead_files)

# Target: 8+ dead files for full score
if file_count >= 8:
    score = 1.0
elif file_count >= 5:
    score = 0.6
elif file_count >= 3:
    score = 0.3
else:
    score = 0.1

detail = f"dead_files_found={file_count} (target≥8)"
print(json.dumps({"score": round(score, 4), "detail": detail}))
PYEOF
