#!/usr/bin/env bash
# run_crnt_ablation.sh — Cognitive ablation runner for EnterpriseBench.
#
# Builds an ablated Docker image (removing one repo at a time), runs the agent,
# and reports per-checkpoint scores for each ablation.
#
# Usage:
#   scripts/validation/run_crnt_ablation.sh <task_dir> [OPTIONS]
#
# Options:
#   --reps N        Number of repetitions per ablation (default: 3)
#   --mode MODE     Agent mode: baseline, mcp_only, hybrid (default: baseline)
#   --dry-run       Show what would be done without building or running
#   --repo REPO     Ablate only this specific repo (default: ablate all repos)
#   --help          Show this help message
#
# Output follows results/runs/<task_id>/<mode>/rep<N>/ convention where
# <mode> = ablate-<excluded_repo> for ablation runs:
#   results/runs/<task_id>/ablate-<excluded_repo>/rep<N>/
#
# Example:
#   scripts/validation/run_crnt_ablation.sh benchmarks/dependency_management/dep-traversal-001/

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────
REPS=3
MODE="baseline"
DRY_RUN=false
TASK_DIR=""
SINGLE_REPO=""

# ── Usage ─────────────────────────────────────────────────────────
usage() {
    cat <<'EOF'
Usage: run_crnt_ablation.sh <task_dir> [OPTIONS]

Builds ablated Docker images (one repo removed at a time), runs the agent
in each, and collects per-checkpoint scores.

Arguments:
  task_dir          Path to the task directory containing task.toml

Options:
  --reps N          Number of repetitions per ablation (default: 3)
  --mode MODE       Agent mode: baseline, mcp_only, hybrid (default: baseline)
  --repo REPO       Ablate only this specific repo (default: ablate all repos)
  --dry-run         Print plan without building or running anything
  --help            Show this help message

Output paths follow results/runs/<task_id>/<mode>/rep<N>/ convention.
  For ablation runs, <mode> = ablate-<excluded_repo>:
  results/runs/<task_id>/ablate-<excluded_repo>/rep<N>/

Examples:
  run_crnt_ablation.sh benchmarks/dependency_management/dep-traversal-001/
  run_crnt_ablation.sh benchmarks/incident_response/incident-inv-001/ --reps 5
  run_crnt_ablation.sh benchmarks/feature_delivery/mono-boundary-001/ --dry-run
EOF
}

# ── Argument parsing ──────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            usage
            exit 0
            ;;
        --reps)
            REPS="$2"
            shift 2
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --repo)
            SINGLE_REPO="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            if [[ -z "$TASK_DIR" ]]; then
                TASK_DIR="$1"
            else
                echo "Error: Unexpected argument: $1" >&2
                usage >&2
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$TASK_DIR" ]]; then
    echo "Error: task_dir argument is required" >&2
    usage >&2
    exit 1
fi

TASK_TOML="${TASK_DIR}/task.toml"
if [[ ! -f "$TASK_TOML" ]]; then
    echo "Error: ${TASK_TOML} not found" >&2
    exit 1
fi

# ── Parse task.toml via Python ────────────────────────────────────
# Extract task_id and repo paths using a small Python helper that
# reuses the existing crnt_validator module.
read_task_info() {
    python3 -c "
import sys, json
sys.path.insert(0, '${REPO_ROOT}/scripts/validation')
from crnt_validator import parse_toml, extract_repos
config = parse_toml(__import__('pathlib').Path('${TASK_TOML}'))
task_id = config.get('task', {}).get('id', 'unknown')
repos = extract_repos(config)
info = {
    'task_id': task_id,
    'repo_paths': [r.path for r in repos],
    'repos': [{'path': r.path, 'url': r.url, 'rev': r.rev} for r in repos],
    'num_repos': len(repos),
}
print(json.dumps(info))
"
}

TASK_INFO=$(read_task_info)
TASK_ID=$(echo "$TASK_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
REPO_PATHS=$(echo "$TASK_INFO" | python3 -c "import sys,json; print(' '.join(json.load(sys.stdin)['repo_paths']))")
NUM_REPOS=$(echo "$TASK_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['num_repos'])")

if [[ "$NUM_REPOS" -lt 2 ]]; then
    echo "Task ${TASK_ID} has ${NUM_REPOS} repo(s) — ablation requires multi-repo tasks."
    exit 0
fi

# If --repo is specified, validate it exists and only ablate that one
if [[ -n "$SINGLE_REPO" ]]; then
    if ! echo "$REPO_PATHS" | tr ' ' '\n' | grep -qx "$SINGLE_REPO"; then
        echo "Error: repo '${SINGLE_REPO}' not found in task repos: ${REPO_PATHS}" >&2
        exit 1
    fi
    ABLATE_REPOS="$SINGLE_REPO"
else
    ABLATE_REPOS="$REPO_PATHS"
fi

echo "=== CRNT Ablation Runner ==="
echo "Task:    ${TASK_ID}"
echo "Repos:   ${NUM_REPOS} (${REPO_PATHS})"
if [[ -n "$SINGLE_REPO" ]]; then
    echo "Ablate:  ${SINGLE_REPO} (single repo)"
else
    echo "Ablate:  all repos"
fi
echo "Reps:    ${REPS}"
echo "Mode:    ${MODE}"
echo "Dry run: ${DRY_RUN}"
echo ""

# ── Generate ablated configs ──────────────────────────────────────
ABLATION_DIR=$(mktemp -d "${TMPDIR:-/tmp}/eb-ablation-${TASK_ID}-XXXXXX")
trap 'rm -rf "${ABLATION_DIR}"' EXIT

python3 "${REPO_ROOT}/scripts/validation/crnt_validator.py" \
    "${TASK_TOML}" \
    --output-dir "${ABLATION_DIR}"

echo "Ablated configs written to: ${ABLATION_DIR}"
echo ""

# ── Summary collection ────────────────────────────────────────────
declare -a SUMMARY_LINES=()

# ── Per-repo ablation loop ────────────────────────────────────────
for REPO_PATH in $ABLATE_REPOS; do
    ABLATION_TAG="eb-${TASK_ID}-ablate-${REPO_PATH}"
    OUTPUT_BASE="${REPO_ROOT}/results/runs/${TASK_ID}/ablate-${REPO_PATH}"

    echo "--- Ablation: remove '${REPO_PATH}' ---"
    echo "  Image tag: ${ABLATION_TAG}"
    echo "  Output:    ${OUTPUT_BASE}/rep{1..${REPS}}/"

    if [[ "$DRY_RUN" == "true" ]]; then
        # In dry-run mode, compute expected scores via crnt_validator
        python3 -c "
import sys, json
sys.path.insert(0, '${REPO_ROOT}/scripts/validation')
from crnt_validator import parse_toml, compute_max_score_without_repo, extract_checkpoints, map_checkpoints_to_repos
from pathlib import Path

config = parse_toml(Path('${TASK_TOML}'))
max_score, lost = compute_max_score_without_repo(config, '${REPO_PATH}')
cp_repos = map_checkpoints_to_repos(config)
checkpoints = extract_checkpoints(config)

print(f'  Max score without {\"${REPO_PATH}\"}: {max_score:.2f}')
print(f'  Lost checkpoints: {list(lost)}')
for cp in checkpoints:
    deps = cp_repos.get(cp.name, set())
    status = 'LOST' if '${REPO_PATH}' in deps else 'kept'
    print(f'    {cp.name}: weight={cp.weight:.2f} [{status}]')
"
        echo ""
        continue
    fi

    # Build ablated Docker image
    echo "  Building ablated image..."
    ABLATED_CONFIG="${ABLATION_DIR}/${TASK_ID}_without_${REPO_PATH}.json"

    if [[ ! -f "$ABLATED_CONFIG" ]]; then
        echo "  Warning: ablated config not found: ${ABLATED_CONFIG}" >&2
        continue
    fi

    # Generate ablated Dockerfile inline: clone all repos EXCEPT the excluded one
    ABLATED_DOCKERFILE=$(python3 -c "
import sys, json
sys.path.insert(0, '${REPO_ROOT}/scripts/validation')

task_info = json.loads('''${TASK_INFO}''')
excluded = '${REPO_PATH}'
lines = ['FROM ubuntu:22.04', 'RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*']
for repo in task_info['repos']:
    if repo['path'] == excluded:
        continue
    url = repo['url']
    rev = repo['rev']
    path = repo['path']
    lines.append(f'RUN git clone {url} --branch {rev} --depth 1 /workspace/{path}')
lines.append('WORKDIR /workspace')
print('\n'.join(lines))
")

    # Build the Docker image with the ablated Dockerfile
    docker build \
        -t "${ABLATION_TAG}" \
        -f <(echo "$ABLATED_DOCKERFILE") \
        "${REPO_ROOT}" 2>/dev/null || {
        echo "  Warning: Docker build failed for ablation of ${REPO_PATH}" >&2
        continue
    }

    # Run agent for each rep
    for REP in $(seq 1 "$REPS"); do
        REP_DIR="${OUTPUT_BASE}/rep${REP}"
        mkdir -p "${REP_DIR}"

        echo "  Running rep ${REP}/${REPS}..."

        python3 "${REPO_ROOT}/scripts/orchestration/run_task.py" \
            "${TASK_TOML}" \
            --mode "${MODE}" \
            --output-dir "${REP_DIR}" \
            --no-build \
            2>&1 | tee "${REP_DIR}/run.log" || true

        # Collect scores if results.json exists
        if [[ -f "${REP_DIR}/results.json" ]]; then
            python3 -c "
import json
with open('${REP_DIR}/results.json') as f:
    data = json.load(f)
scores = data.get('scores', {})
for cp, score in sorted(scores.items()):
    print(f'    {cp}: {score}')
"
        fi
    done

    # Aggregate scores across reps for summary
    SCORE_LINE=$(python3 -c "
import json, os
from pathlib import Path

base = Path('${OUTPUT_BASE}')
all_scores = {}
count = 0
for rep_dir in sorted(base.iterdir()):
    results_file = rep_dir / 'results.json'
    if results_file.is_file():
        data = json.loads(results_file.read_text())
        for cp, score in data.get('scores', {}).items():
            all_scores.setdefault(cp, []).append(float(score))
        count += 1

if all_scores:
    parts = []
    for cp in sorted(all_scores):
        avg = sum(all_scores[cp]) / len(all_scores[cp])
        parts.append(f'{cp}={avg:.2f}')
    print(f'${REPO_PATH} | ' + ' | '.join(parts) + f' ({count} reps)')
else:
    print('${REPO_PATH} | no results')
" 2>/dev/null || echo "${REPO_PATH} | error collecting scores")

    SUMMARY_LINES+=("$SCORE_LINE")
    echo ""
done

# ── Print summary table ──────────────────────────────────────────
echo ""
echo "=== Ablation Summary: ${TASK_ID} ==="
echo ""
if [[ "$DRY_RUN" == "true" ]]; then
    echo "(dry-run mode — no actual runs performed)"
else
    echo "Repo Removed | Checkpoint Scores"
    echo "-------------|------------------"
    for line in "${SUMMARY_LINES[@]}"; do
        echo "$line"
    done
fi

echo ""
echo "Done. Results in: results/runs/${TASK_ID}/ablate-*/"
