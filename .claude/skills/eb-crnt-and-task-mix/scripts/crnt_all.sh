#!/usr/bin/env bash
# crnt_all.sh — read-only diagnostic: run the structural CRNT validator over
# every active task.toml (excluding benchmarks/_archived/) and print failures.
#
# Exists because `make verify-crnt` is broken as of 2026-07-07: the Makefile
# invokes scripts/validation/crnt_validator.py with no argument, but the
# validator requires a task.toml path. This script supplies the loop.
#
# Usage (from anywhere):
#   .claude/skills/eb-crnt-and-task-mix/scripts/crnt_all.sh
#
# Output: one "CRNT FAIL (rc=N): <path>" line per failing task, then a summary.
#   rc=2  task fails the structural CRNT (a declared repo has zero
#         ground_truth.required_files entries)
#   rc=1  validator error (missing/unparseable task.toml)
# Single-repo tasks exit 0 (CRNT does not apply) and are counted as skipped-ok.
#
# Exit code: 0 if every active task passes/skips, 1 if any task fails.
# This script writes nothing and mutates nothing.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"

fail_count=0
total=0
while IFS= read -r task_toml; do
    total=$((total + 1))
    rc=0
    python3 scripts/validation/crnt_validator.py "$task_toml" >/dev/null 2>&1 || rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "CRNT FAIL (rc=${rc}): ${task_toml}"
        fail_count=$((fail_count + 1))
    fi
done < <(find benchmarks -name task.toml -not -path "*_archived*" | sort)

echo "CRNT sweep: ${total} active tasks checked, ${fail_count} failing."
[ "$fail_count" -eq 0 ] || exit 1
exit 0
