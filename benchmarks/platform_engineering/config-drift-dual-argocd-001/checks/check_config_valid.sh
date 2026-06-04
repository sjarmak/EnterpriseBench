#!/usr/bin/env bash
# Checkpoint 3: Validate corrected configuration if provided
# No-helm fallback uses bash + jq + grep (no python3 in container). Port-consistency
# check is identical to the previous python: flag a line as inconsistent when it
# contains 'serflan' (case-insensitive) AND literal 'serfWAN', or contains 'serfwan'
# (case-insensitive) AND literal 'serfLAN' but not literal 'serfWAN'.
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
  check_consul_ports() {
    local service_file="$CHART_DIR/templates/consul-headless-service.yaml"
    local line line_lc
    while IFS= read -r line || [[ -n "$line" ]]; do
      line_lc=$(printf '%s' "$line" | tr '[:upper:]' '[:lower:]')
      if printf '%s' "$line_lc" | grep -qF -- 'serflan' && printf '%s' "$line" | grep -qF -- 'serfWAN'; then
        return 1
      fi
      if printf '%s' "$line_lc" | grep -qF -- 'serfwan' && printf '%s' "$line" | grep -qF -- 'serfLAN' && ! printf '%s' "$line" | grep -qF -- 'serfWAN'; then
        return 1
      fi
    done < "$service_file"
    return 0
  }
  if check_consul_ports 2>/dev/null; then
    printf '{"score": 1.0, "passed": true, "reason": "Corrected config has consistent port references"}\n'
  else
    printf '{"score": 0.25, "passed": false, "reason": "Corrected config still has inconsistent port references"}\n'
  fi
fi
