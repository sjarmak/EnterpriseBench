#!/usr/bin/env bash
# Checkpoint 3: Validate corrected configuration if provided
set -euo pipefail

export WORKSPACE="${WORKSPACE:-/workspace}"
export CHART_DIR="$WORKSPACE/charts/bitnami/consul"
export REPORT="$WORKSPACE/charts/DRIFT_REPORT.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# Check if corrected config files were provided
export CORRECTED_SERVICE="$CHART_DIR/templates/consul-headless-service.yaml"
if [[ ! -f "$CORRECTED_SERVICE" ]]; then
  # No corrected config is optional — give partial credit for the report alone
  printf '{"score": 1.0, "passed": true, "reason": "Corrected config not provided (optional checkpoint — skipped)"}\n'
  exit 0
fi

# If helm is available, try to template the corrected chart
if command -v helm &>/dev/null; then
  if helm template test-consul "$CHART_DIR" --dry-run 2>/dev/null | grep -q 'kind:'; then
    printf '{"score": 1.0, "passed": true, "reason": "Corrected chart templates successfully"}\n'
  else
    printf '{"score": 0.25, "passed": false, "reason": "Corrected chart fails helm template"}\n'
  fi
else
  # No helm available — check that the corrected file has consistent port references
  if python3 -c "
import os
service_file = os.path.join(os.environ['CHART_DIR'], 'templates', 'consul-headless-service.yaml')
content = open(service_file).read()
# Basic check: serflan-udp should reference serfLAN, serfwan-udp should reference serfWAN
lines = content.split('\n')
ok = True
for i, line in enumerate(lines):
    if 'serflan' in line.lower() and 'serfWAN' in line:
        ok = False
    if 'serfwan' in line.lower() and 'serfLAN' in line and 'serfWAN' not in line:
        ok = False
exit(0 if ok else 1)
" 2>/dev/null; then
    printf '{"score": 1.0, "passed": true, "reason": "Corrected config has consistent port references"}\n'
  else
    printf '{"score": 0.25, "passed": false, "reason": "Corrected config still has inconsistent port references"}\n'
  fi
fi
