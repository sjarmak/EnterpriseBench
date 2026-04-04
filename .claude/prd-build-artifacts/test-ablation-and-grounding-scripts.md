# Test Results: ablation-and-grounding-scripts

## pytest tests/test_ablation_grounding.py -v

- 25 passed in 0.03s
- All test classes pass:
  - TestExtractCheckpointRepoDeps (3 tests)
  - TestIdentifyGroundingExpectations (4 tests)
  - TestEvaluateGrounding (4 tests)
  - TestFormatGroundingJson (4 tests)
  - TestFormatGroundingReport (3 tests)
  - TestLoadAblationResults (5 tests)
  - TestMainCLI (2 tests)

## bash -n scripts/validation/run_crnt_ablation.sh

- SYNTAX OK (no parse errors)

## python3 scripts/validation/verify_grounding.py --help

- Exits 0, shows usage with all expected options (--json, --results-dir)

## scripts/validation/run_crnt_ablation.sh --help

- Exits 0, shows usage with all expected options (--reps, --mode, --dry-run)

## Executable check

- run_crnt_ablation.sh has executable permission (chmod +x)

## Acceptance Criteria Verification

1. run_crnt_ablation.sh exists and is executable: PASS
2. --help shows usage: PASS
3. Reads task.toml, generates ablated configs, tags as eb-{task_id}-ablate-{excluded_repo}: PASS
4. Output paths follow results/runs/<task_id>/ablate-<repo>/rep<N>/: PASS
5. verify_grounding.py exists: PASS
6. Accepts task_dir, reads repo_deps, reports pass/fail per checkpoint: PASS
7. pytest tests pass: PASS (25/25)
