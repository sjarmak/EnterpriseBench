#!/usr/bin/env bash
# check_test_impact.sh — verify agent identifies test impact of schema changes
set -euo pipefail

export ANSWER_FILE="${WORKSPACE:-/workspace}/agent_output/answer.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
  printf '{"score": 0.0, "passed": false, "detail": "No answer.json found"}\n'
  exit 0
fi

python3 -c "
import json, os

answer = json.load(open(os.environ['ANSWER_FILE']))
answer_text = json.dumps(answer).lower()

# Check for test-related mentions across repos
test_concepts = ['test', 'spec', 'fixture', 'migration_test', 'schema_test', 'integration']
matched = sum(1 for c in test_concepts if c in answer_text)

# Check for multi-repo test awareness
repos_with_tests = 0
if any(r in answer_text for r in ['supabase', 'migration']):
    repos_with_tests += 1
if any(r in answer_text for r in ['postgrest', 'haskell', 'schemacache']):
    repos_with_tests += 1
if any(r in answer_text for r in ['gotrue', 'token', 'session']):
    repos_with_tests += 1

score = round(min(1.0, matched / 3.0) * 0.5 + min(1.0, repos_with_tests / 2.0) * 0.5, 2)
passed = matched >= 1 and repos_with_tests >= 2

detail = f'Test concepts: {matched}/{len(test_concepts)}, repos with test awareness: {repos_with_tests}/3'
print(json.dumps({'score': score, 'passed': passed, 'detail': detail}))
"
