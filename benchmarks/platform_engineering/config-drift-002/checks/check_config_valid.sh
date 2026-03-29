#!/usr/bin/env bash
# Checkpoint 3: Validate corrected configuration if provided
set -euo pipefail

export WORKSPACE="${WORKSPACE:-/workspace}"
export CHART_DIR="$WORKSPACE/charts/bitnami/spring-cloud-dataflow"
export REPORT="$WORKSPACE/charts/DRIFT_REPORT.json"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DRIFT_REPORT.json not found"}\n'
  exit 0
fi

# Check if any corrected config files exist
export HAS_CORRECTED=false
for f in "$CHART_DIR/values.yaml" "$CHART_DIR/templates/_helpers.tpl" "$CHART_DIR/templates/externalrabbitmq-secrets.yaml"; do
  if [[ -f "$f" ]]; then
    HAS_CORRECTED=true
    break
  fi
done

if [[ "$HAS_CORRECTED" = false ]]; then
  printf '{"score": 1.0, "passed": true, "reason": "Corrected config not provided (optional checkpoint — skipped)"}\n'
  exit 0
fi

# If helm is available, try to template
if command -v helm &>/dev/null; then
  if helm dependency build "$CHART_DIR" 2>/dev/null && helm template test-scdf "$CHART_DIR" --dry-run 2>/dev/null | grep -q 'kind:'; then
    printf '{"score": 1.0, "passed": true, "reason": "Corrected chart templates successfully"}\n'
  else
    printf '{"score": 0.25, "passed": false, "reason": "Corrected chart fails helm template"}\n'
  fi
else
  # No helm — check that values.yaml has the expected new parameters
  if python3 -c "
import os
values_file = os.path.join(os.environ['CHART_DIR'], 'values.yaml')
if not os.path.exists(values_file):
    exit(1)
content = open(values_file).read()
# Check for existence of secret key configuration parameter
if 'existingSecretPasswordKey' in content or 'existingPasswordSecretKey' in content or 'secretKey' in content:
    exit(0)
exit(1)
" 2>/dev/null; then
    printf '{"score": 1.0, "passed": true, "reason": "Corrected values.yaml includes secret key parameter"}\n'
  else
    printf '{"score": 0.25, "passed": false, "reason": "Corrected config missing expected parameters"}\n'
  fi
fi
