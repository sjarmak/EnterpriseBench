#!/usr/bin/env bash
# Checkpoint 2: Verify impact classification
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/babel/IMPACT_REPORT.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

python3 -c "
import re, json, sys

with open('${REPORT}') as f:
    content = f.read().lower()

# Three required signals from the ground truth:
#   1. Changed construct name: TSPropertySignature or initializer
#   2. Semver level: patch
#   3. Package reference: @babel/types (or babel/types or babel-types)
signals = {
    'construct': bool(re.search(r'tspropertysi[g]nature|initializer', content)),
    'semver':    bool(re.search(r'\bpatch\b', content)),
    'package':   bool(re.search(r'@babel/types|babel[/-]types', content)),
}

matched = sum(signals.values())

# Score is proportional to how many signals are present (out of 3)
score = round(matched / 3.0, 2)

# Must have at least 2 of the 3 signals to pass
passed = matched >= 2

reason_parts = [k for k, v in signals.items() if v]
missing_parts = [k for k, v in signals.items() if not v]

reason = (
    f'Matched {matched}/3 required signals '
    f'(found: {reason_parts}; missing: {missing_parts})'
)

print(json.dumps({'score': score, 'passed': passed, 'reason': reason}))
"
