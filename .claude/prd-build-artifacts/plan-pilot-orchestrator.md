# Plan: pilot-orchestrator

## Files to Create

1. `configs/pilot_manifest.json` — 48 run entries
2. `scripts/orchestration/run_pilot.py` — batch orchestrator
3. `tests/test_pilot_orchestrator.py` — pytest test suite

## configs/pilot_manifest.json

JSON array of 48 objects. Each entry:

- task_id, task_dir, mode, rep_index (1-3), account_id (1-5 round-robin), output_dir

Order: 36 full runs first (4 tasks x 3 modes x 3 reps), then 12 ablation runs (2 tasks x 2 repos x 3 reps).
Account IDs assigned 1-5 round-robin across all 48 entries sequentially.

## scripts/orchestration/run_pilot.py

- argparse CLI: --manifest (required), --dry-run, --max-parallel (default 5)
- Frozen dataclasses: RunEntry, RunResult
- Load and validate manifest JSON
- Group by account_id for parallel execution
- For full runs: invoke run_task.py with appropriate args
- For ablation runs: invoke run_crnt_ablation.sh
- Track results in results/phase1_pilot/run_manifest.json
- Produce summary CSV: results/phase1_pilot/summary.csv
- Use subprocess for execution, concurrent.futures for parallelism

## tests/test_pilot_orchestrator.py

- test_load_manifest: loads pilot_manifest.json, validates 48 entries
- test_manifest_structure: all required fields present
- test_account_round_robin: account_ids cycle 1-5
- test_output_path_convention: paths match expected pattern
- test_dry_run: no side effects
- test_run_manifest_creation: writes run_manifest.json
- test_manifest_entry_count: exactly 48
