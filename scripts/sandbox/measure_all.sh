#!/usr/bin/env bash
# measure_all.sh — Build and measure all example task sandboxes.
# Reports disk footprint, clone time, and build feasibility for each.
#
# Usage: bash scripts/sandbox/measure_all.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=============================================="
echo "  EnterpriseBench Sandbox Measurement Report"
echo "=============================================="
echo "Date: $(date -Iseconds)"
echo ""

TASKS=(
    "$REPO_ROOT/benchmarks/EXAMPLE_TASK.toml"
    "$REPO_ROOT/benchmarks/EXAMPLE_TASK_PYTHON.toml"
)

RESULTS_DIR="$REPO_ROOT/scripts/sandbox/.measurements"
mkdir -p "$RESULTS_DIR"

for task_toml in "${TASKS[@]}"; do
    task_name=$(basename "$task_toml" .toml)
    echo "====== $task_name ======"
    echo "File: $task_toml"

    output_dir="$RESULTS_DIR/$task_name"
    mkdir -p "$output_dir"

    echo ""
    echo "--- Generating Dockerfile ---"
    python3 "$SCRIPT_DIR/sandbox_builder.py" "$task_toml" \
        --output-dir "$output_dir" \
        --measure 2>&1 | tee "$output_dir/build_log.txt"

    echo ""
    echo "--- Cleaning up image ---"
    task_id=$(python3 -c "
import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)
with open('$task_toml', 'rb') as f:
    t = tomllib.load(f)
print(t.get('task', {}).get('id', 'unknown'))
")
    docker rmi "eb-sandbox-${task_id}" 2>/dev/null || true

    echo ""
    echo "====== End $task_name ======"
    echo ""
done

echo "=============================================="
echo "  Measurement complete."
echo "  Results in: $RESULTS_DIR/"
echo "=============================================="
