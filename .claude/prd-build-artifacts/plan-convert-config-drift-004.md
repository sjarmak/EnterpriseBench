# Plan: convert-config-drift-004

## Changes

### 1. task.toml

- Change `difficulty_stratum` from "large_single" to "dual_repo"
- Add second `[[repos]]`: url="https://github.com/dandydeveloper/charts", rev="redis-ha-4.26.6", path="dandydeveloper-charts", role="upstream"
- Add `repo_deps` to each checkpoint:
  - identify_drift_points: ["argo-cd"]
  - determine_expected_values: ["argo-cd", "dandydeveloper-charts"]
  - validate_corrected_config: ["argo-cd", "dandydeveloper-charts"]
- Update metadata.dependency_depth to 2 (already 2, confirm)
- Update tool_access.expected_mcp_benefit to "high"
- Add ground_truth.required_files for dandydeveloper-charts (charts/redis-ha/values.yaml)
- Add ground_truth.sufficient_files for dandydeveloper-charts (charts/redis-ha/Chart.yaml)

### 2. instruction.md

- Reference /workspace/dandydeveloper-charts/ as the upstream chart repo
- Update override hierarchy trace to explicitly reference upstream repo path

### 3. task.toml prompt

- Update prompt to reference /workspace/dandydeveloper-charts/ for upstream defaults

## CRNT Verification

- Remove argo-cd: score=0.0 (all checkpoints depend on it) -> passes threshold
- Remove dandydeveloper-charts: score=0.40 (only identify_drift_points survives) -> passes threshold
- Result: passes_crnt=true
