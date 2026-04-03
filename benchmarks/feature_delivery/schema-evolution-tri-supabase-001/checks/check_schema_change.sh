#!/usr/bin/env bash
# check_schema_change.sh — verify agent identifies the schema migration in Supabase
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

python3 -c "
import json, os

gt = json.load(open(os.environ['GT_FILE']))
answer = json.load(open(os.environ['ANSWER_FILE']))

gt_files = [f['path'] for f in gt.get('required_files', []) if f.get('repo') == 'supabase']
agent_files = answer.get('source_files', answer.get('files', answer.get('schema_files', [])))

if isinstance(agent_files, list):
    agent_text = ' '.join(str(f) for f in agent_files)
else:
    agent_text = str(agent_files)

found = sum(1 for gt_f in gt_files if gt_f in agent_text or gt_f.split('/')[-1] in agent_text)
score = found / max(len(gt_files), 1)

# Also check for schema-related keywords
keywords = ['auth.users', 'auth.sessions', 'rls', 'migration', 'schema']
kw_match = sum(1 for kw in keywords if kw in json.dumps(answer).lower())
kw_score = min(1.0, kw_match / 3.0)

final_score = round(score * 0.6 + kw_score * 0.4, 2)
passed = final_score >= 0.4
detail = f'Found {found}/{len(gt_files)} schema files, {kw_match}/{len(keywords)} keywords'
print(json.dumps({'score': final_score, 'passed': passed, 'detail': detail}))
"
