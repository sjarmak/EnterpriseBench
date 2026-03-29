#!/usr/bin/env bash
# Checkpoint 2: Verify topological ordering of proposed refactor plan
set -euo pipefail

ANSWER="${WORKSPACE:-/workspace}/REFACTOR_PLAN.md"
GT="${TASK_DIR:-$(dirname "$(dirname "$0")")}/ground_truth.json"

if [[ ! -f "$ANSWER" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "REFACTOR_PLAN.md not found"}\n'
  exit 0
fi

if [[ ! -f "$GT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "ground_truth.json not found"}\n'
  exit 0
fi

# Extract ordered repo list from agent's plan (numbered list items)
PROPOSED_FILE=$(mktemp)
grep -oE '^\s*[0-9]+\.\s+\S+' "$ANSWER" | sed 's/^[[:space:]]*[0-9]*\.\s*//' | head -20 > "$PROPOSED_FILE"

if [[ ! -s "$PROPOSED_FILE" ]]; then
  rm -f "$PROPOSED_FILE"
  printf '{"score": 0.0, "passed": false, "reason": "No numbered ordering found in plan"}\n'
  exit 0
fi

# Determine lib path (4 levels up from checks/ dir)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB_DIR="$(cd "$SCRIPT_DIR/../../../../lib" 2>/dev/null && pwd || echo "")"

export GT_FILE="$GT"
export PROPOSED_FILE

python3 - "$LIB_DIR" <<'PYEOF'
import json, sys, os

lib_dir = sys.argv[1]
if lib_dir:
    sys.path.insert(0, lib_dir)

with open(os.environ['GT_FILE']) as f:
    gt = json.load(f)

with open(os.environ['PROPOSED_FILE']) as f:
    proposed = [r.strip() for r in f if r.strip()]

dep_graph = gt.get('dependency_graph', {})

from eb_verify.plugins.topological_order import validate_topological_order

result = validate_topological_order(proposed, dep_graph)
score = result['score']
passed = score >= 0.5
print(json.dumps({'score': score, 'passed': passed, 'reason': result['detail']}))
PYEOF

rm -f "$PROPOSED_FILE"
