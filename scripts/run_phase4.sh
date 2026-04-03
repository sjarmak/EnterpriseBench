#!/usr/bin/env bash
# Phase 4 Task Expansion Runner (parallel)
# Reads task list from configs/phase4_expansion.txt
# Skips tasks that already have results.json in results/runs/<task_id>/
# Each account supports up to 6 concurrent tasks. Total parallelism = accounts * 6.
# Tasks are distributed round-robin across accounts.
#
# Usage:
#   ./scripts/run_phase4.sh --account 1-5              # 30 parallel (5 accounts x 6)
#   ./scripts/run_phase4.sh --account 1-5 -j 15        # cap at 15 parallel
#   ./scripts/run_phase4.sh --account 1-5 --dry-run    # preview without executing
#   ./scripts/run_phase4.sh --account 1 -j 1           # sequential fallback
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TASK_LIST="$PROJECT_ROOT/configs/phase4_expansion.txt"
LOG_DIR="$PROJECT_ROOT/results/phase4_logs"
mkdir -p "$LOG_DIR"

# ── Parse our flags (extract --account, -j, --dry-run; rest passed through) ──
ACCOUNTS=()
SLOTS_PER_ACCOUNT=6
PARALLEL=0  # 0 = auto (accounts * SLOTS_PER_ACCOUNT)
DRY_RUN=false
MODE="baseline"
PASSTHROUGH=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --account)
            # Parse account spec: "1-5" or "1,3,5" or "1"
            IFS=',' read -ra parts <<< "$2"
            for part in "${parts[@]}"; do
                if [[ "$part" == *-* ]]; then
                    lo="${part%-*}"; hi="${part#*-}"
                    for ((i=lo; i<=hi; i++)); do ACCOUNTS+=("$i"); done
                else
                    ACCOUNTS+=("$part")
                fi
            done
            shift 2 ;;
        -j|--parallel)
            PARALLEL="$2"; shift 2 ;;
        --dry-run)
            DRY_RUN=true; shift ;;
        --mode)
            MODE="$2"; PASSTHROUGH+=("--mode" "$2"); shift 2 ;;
        *)
            PASSTHROUGH+=("$1"); shift ;;
    esac
done

if [[ ${#ACCOUNTS[@]} -eq 0 ]]; then
    echo "ERROR: --account is required (e.g. --account 1-5)"
    exit 1
fi

# Auto-set parallelism: 6 slots per account
if [[ "$PARALLEL" -eq 0 ]]; then
    PARALLEL=$(( ${#ACCOUNTS[@]} * SLOTS_PER_ACCOUNT ))
fi

echo "Phase 4 Expansion"
echo "  Accounts: ${ACCOUNTS[*]} (${#ACCOUNTS[@]} accounts x $SLOTS_PER_ACCOUNT slots = $((${#ACCOUNTS[@]} * SLOTS_PER_ACCOUNT)) max)"
echo "  Parallel workers: $PARALLEL"
echo "  Mode: $MODE"
echo ""

# ── Preflight: validate tokens, Docker, disk ──
echo "Running preflight checks (with token refresh)..."
if ! python3 "$PROJECT_ROOT/scripts/infra/check_infra.py" --refresh-tokens; then
    echo ""
    echo "ERROR: Preflight failed. Fix the issues above before launching."
    echo "  To refresh tokens: python3 scripts/infra/headless_login.py --account N"
    exit 1
fi
echo ""

# ── Parse task list ──
tasks=()
while IFS= read -r line; do
    line="$(echo "$line" | sed 's/#.*//' | xargs)"
    [[ -z "$line" ]] && continue
    tasks+=("$line")
done < "$TASK_LIST"

echo "Task list: ${#tasks[@]} tasks"

# ── Separate pending vs already-done ──
pending_paths=()
pending_ids=()
skipped=0
for toml_path in "${tasks[@]}"; do
    task_id=$(grep '^id = ' "$PROJECT_ROOT/$toml_path" | head -1 | sed 's/id = "//;s/"//')
    results_file="$PROJECT_ROOT/results/runs/$task_id/results.json"
    if [[ -f "$results_file" ]]; then
        score=$(python3 -c "import json; d=json.load(open('$results_file')); print(d.get('scores',{}).get('task_score','?'))" 2>/dev/null || echo "?")
        echo "  skip: $task_id (score=$score)"
        skipped=$((skipped + 1))
    else
        pending_paths+=("$toml_path")
        pending_ids+=("$task_id")
    fi
done

echo ""
echo "Already scored: $skipped"
echo "Pending: ${#pending_paths[@]}"

if [[ ${#pending_paths[@]} -eq 0 ]]; then
    echo "All tasks already scored!"
    exit 0
fi

# Build per-account task counts for display
declare -A acct_count
for i in "${!pending_ids[@]}"; do
    acct=${ACCOUNTS[$((i % ${#ACCOUNTS[@]}))]}
    acct_count[$acct]=$(( ${acct_count[$acct]:-0} + 1 ))
    echo "  [$((i+1))] ${pending_ids[$i]} -> account$acct"
done
echo ""
echo "Per-account load:"
for acct in "${ACCOUNTS[@]}"; do
    echo "  account$acct: ${acct_count[$acct]:-0} tasks"
done
echo ""

if $DRY_RUN; then
    echo "[dry-run] Would run ${#pending_paths[@]} tasks across ${#ACCOUNTS[@]} accounts with $PARALLEL workers"
    exit 0
fi

# ── Run tasks in parallel using background jobs ──
# Track PIDs and their task IDs for reporting
declare -A pid_to_task
active_pids=()
completed=0
errors=0
total=${#pending_paths[@]}

# Function to wait for a slot when at max parallelism
wait_for_slot() {
    while [[ ${#active_pids[@]} -ge $PARALLEL ]]; do
        # Wait for any one child to finish
        local done_pid
        for idx in "${!active_pids[@]}"; do
            pid="${active_pids[$idx]}"
            if ! kill -0 "$pid" 2>/dev/null; then
                # Process finished — check exit code
                wait "$pid" && status=0 || status=$?
                task_id="${pid_to_task[$pid]}"
                if [[ $status -eq 0 ]]; then
                    completed=$((completed + 1))
                    echo "$(date +%H:%M:%S) ✓ $task_id completed [$((completed + errors))/$total]"
                else
                    errors=$((errors + 1))
                    echo "$(date +%H:%M:%S) ✗ $task_id failed (exit=$status) [$((completed + errors))/$total]"
                fi
                unset 'active_pids[$idx]'
                unset "pid_to_task[$pid]"
                # Re-index array to remove gaps
                active_pids=("${active_pids[@]+"${active_pids[@]}"}")
                return
            fi
        done
        sleep 2
    done
}

echo "$(date +%H:%M:%S) Starting $total tasks with $PARALLEL parallel workers"
echo ""

for i in "${!pending_paths[@]}"; do
    wait_for_slot

    toml_path="${pending_paths[$i]}"
    task_id="${pending_ids[$i]}"
    acct=${ACCOUNTS[$((i % ${#ACCOUNTS[@]}))]}
    log_file="$LOG_DIR/${task_id}.log"

    echo "$(date +%H:%M:%S) ▶ $task_id (account$acct) [slot $((${#active_pids[@]} + 1))/$PARALLEL]"

    # Launch in background, log to file
    python3 "$PROJECT_ROOT/scripts/run_benchmark.py" \
        "$PROJECT_ROOT/$toml_path" \
        --account "$acct" \
        "${PASSTHROUGH[@]}" \
        > "$log_file" 2>&1 &

    pid=$!
    active_pids+=("$pid")
    pid_to_task[$pid]="$task_id"
done

# Wait for remaining tasks
while [[ ${#active_pids[@]} -gt 0 ]]; do
    wait_for_slot
done

# Final drain — catch any stragglers
wait 2>/dev/null || true

echo ""
echo "━━━ Phase 4 Summary ━━━"
echo "Completed: $completed"
echo "Errors: $errors"
echo "Previously scored: $skipped"
echo "Total scored: $((completed + skipped))"
echo "Logs: $LOG_DIR/"

# Print score summary for newly completed tasks
echo ""
echo "━━━ New Scores ━━━"
for task_id in "${pending_ids[@]}"; do
    results_file="$PROJECT_ROOT/results/runs/$task_id/results.json"
    if [[ -f "$results_file" ]]; then
        python3 -c "
import json
d = json.load(open('$results_file'))
s = d.get('scores', {})
score = s.get('task_score', '?')
total = s.get('checkpoints_total', '?')
passed = s.get('checkpoints_passed', '?')
print(f'  {\"$task_id\":<50} {score}/{total} (passed={passed})')
" 2>/dev/null || echo "  $task_id: error reading results"
    else
        echo "  $task_id: no results"
    fi
done
