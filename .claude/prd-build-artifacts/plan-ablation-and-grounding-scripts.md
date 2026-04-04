# Plan: ablation-and-grounding-scripts

## 1. run_crnt_ablation.sh

Shell script that orchestrates Docker-based ablation runs.

### Interface

- `run_crnt_ablation.sh <task_dir> [--reps N] [--mode MODE] [--dry-run] [--help]`
- Defaults: reps=3, mode=baseline

### Logic

1. Parse task.toml (extract task_id, repos list) using python helper
2. For each repo in the task:
   a. Call crnt_validator.py to generate ablated config JSON (--output-dir)
   b. Generate ablated Dockerfile from the config (exclude that repo's clone)
   c. Build Docker image tagged `eb-{task_id}-ablate-{excluded_repo}`
   d. For each rep 1..N:
   - Run agent in container
   - Collect results to `results/runs/{task_id}/ablate-{excluded_repo}/rep{N}/`
     e. Collect per-checkpoint scores from verifier output
3. Print summary table: repo_removed | checkpoint | score

### Implementation notes

- Use python one-liners or a small helper to parse TOML (avoid complex bash TOML parsing)
- --dry-run prints what would happen without building/running
- --help shows usage

## 2. verify_grounding.py

Python script that validates verifier grounding against ablation.

### Interface

- `verify_grounding.py <task_dir> [--json]`

### Logic

1. Parse task.toml, extract checkpoints and their repo_deps (using crnt_validator functions)
2. Use `map_checkpoints_to_repos()` to get checkpoint->repo mapping
3. For each repo that appears in any checkpoint's deps:
   a. Identify checkpoints anchored to that repo
   b. Compute expected result: checkpoint should FAIL when its anchored repo is absent
   c. Check if ablation results exist, or run verifiers in ablated mode
   d. Report pass/fail per checkpoint
4. Output text table or --json

### Key functions (testable)

- `extract_checkpoint_repo_deps(config)` -> dict mapping checkpoint names to repo deps
- `identify_grounding_expectations(config)` -> list of (checkpoint, repo, expected_fail)
- `evaluate_grounding(config, ablation_results)` -> list of GroundingResult
- `format_grounding_report(results)` -> str
- `format_grounding_json(results)` -> str

## 3. tests/test_ablation_grounding.py

Unit tests for verify_grounding.py Python functions:

- Test `extract_checkpoint_repo_deps` with multi-repo config
- Test `identify_grounding_expectations` logic
- Test `evaluate_grounding` pass/fail classification
- Test JSON output formatting
- Test edge cases: single-repo task, checkpoints without repo_deps
