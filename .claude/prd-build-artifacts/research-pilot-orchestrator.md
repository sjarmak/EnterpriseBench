# Research: pilot-orchestrator

## Existing Infrastructure

### run_task.py

- Single-session task runner: builds Docker sandbox, runs agent, scores result
- Uses `TaskRunConfig` (frozen dataclass) and `TaskRunResult` dataclass
- Accepts `--mode` (baseline/mcp_only/hybrid), `--account` for credential routing
- Task TOML path as positional argument, `--output-dir` for results
- Validates session_type = "single"

### run_crnt_ablation.sh

- Bash script for ablation runs
- Takes `<task_dir>` positional, `--reps N`, `--mode MODE`, `--dry-run`
- Output: `results/runs/<task_id>/ablate-<excluded_repo>/rep<N>/`
- Iterates over repos, removes one at a time, builds ablated Docker image, runs agent

### sweep_manifest.json

- Existing manifest format: items array with task_id, mode, suite, difficulty, status, results_path
- 240 combinations (80 per mode)

## Pilot Tasks (4)

1. **incident-inv-docker-shutdown-004** — `benchmarks/incident_response/incident-investigation-004/`
   - Repos: moby (primary), containerd (dependency)
2. **error-trace-k8s-nftables-sync-001** — `benchmarks/customer_escalation/err-provenance-02/`
   - Repos: kubernetes (primary), knftables (dependency)
3. **support-map-grafana-alerts-004** — `benchmarks/customer_escalation/support-mapping-004/`
   - Repos: grafana (primary), alertmanager (dependency)
4. **config-drift-argocd-redis-ha-004** — `benchmarks/platform_engineering/config-drift-004/`
   - Repos: argo-cd (primary), dandydeveloper-charts (upstream)

## Run Breakdown (48 total)

### Full runs (36): 4 tasks x 3 modes x 3 reps

### Ablation runs (12): 2 tasks x 2 repos x 3 reps

- incident-inv-docker-shutdown-004: ablate-moby, ablate-containerd
- support-map-grafana-alerts-004: ablate-grafana, ablate-alertmanager
