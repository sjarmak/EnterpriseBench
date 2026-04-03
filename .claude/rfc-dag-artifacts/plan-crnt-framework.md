# CRNT Framework Implementation Plan

## Step 1: Create scripts/validation/**init**.py

Empty init file for the package.

## Step 2: Create scripts/validation/crnt_validator.py

1. TOML parsing: use tomllib/tomli with same fallback pattern as create_sg_mirrors.py
2. `load_task(path) -> dict`: Parse task.toml
3. `generate_ablations(task_config) -> list[AblatedConfig]`: For each repo, create config with that repo removed
4. `compute_max_score_without_repo(task_config, removed_repo) -> float`:
   - Map checkpoints to repos via ground_truth.required_files
   - If a checkpoint depends on removed repo, score contribution = 0
   - Sum remaining checkpoint weights
5. `evaluate_crnt(task_config) -> CRNTResult`:
   - For each repo, compute max score without that repo
   - Task passes CRNT if removing ANY single repo → score ≤ 0.60
6. CLI with argparse:
   - Positional: task.toml path
   - `--dry-run`: show ablations without writing
   - `--output-dir`: write ablated configs to directory
   - `--threshold`: CRNT threshold (default 0.60)

## Step 3: Write tests

- Test TOML parsing
- Test ablation generation (correct number, correct repos removed)
- Test score computation (anchored vs unanchored checkpoints)
- Test CRNT pass/fail criteria
