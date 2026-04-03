# Plan: convert-support-mapping-004

## Goal

Convert support-mapping-004 from single-repo (grafana) to dual-repo (grafana + alertmanager).

## Changes

### 1. task.toml

- Change difficulty_stratum to "dual_repo"
- Add [[repos]] for alertmanager (v0.26.0, role=dependency)
- Add repo_deps to each checkpoint per spec
- Update metadata: dependency_depth=2, add "alertmanager" to frameworks
- Update tool_access: expected_mcp_benefit="high", update rationale
- Add alertmanager entries to ground_truth.required_files and sufficient_files

### 2. instruction.md

- Expand customer ticket to mention notification delivery failures (alertmanager territory)
- Reference /workspace/alertmanager/ for investigation

### 3. ground_truth.json

- Add alertmanager files to required_files and sufficient_files
- Add alertmanager-related ownership keywords and related references

### 4. Check scripts

- Update check_related_issues.sh to verify alertmanager references found
- Other check scripts are generic (keyword/path matching) and need no changes

### 5. Validation

- Run CRNT validator, confirm passes_crnt=true
