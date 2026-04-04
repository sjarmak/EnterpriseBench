# Test Results: convert-config-drift-004

## CRNT Validator

- **passes_crnt**: true
- Remove argo-cd: max_score=0.0, lost all 3 checkpoints -> passes threshold (<=0.60)
- Remove dandydeveloper-charts: max_score=0.40, lost 2 checkpoints -> passes threshold (<=0.60)

## Shell Script Validation

- check_drift_points.sh: syntax valid
- check_expected_values.sh: syntax valid
- check_config_valid.sh: syntax valid

## Acceptance Criteria

1. difficulty_stratum = "dual_repo" -- PASS
2. 2 [[repos]] entries (argo-cd + dandydeveloper-charts) -- PASS
3. repo_deps: identify_drift_points=["argo-cd"], others=["argo-cd","dandydeveloper-charts"] -- PASS
4. ground_truth.required_files includes both repos -- PASS
5. CRNT passes_crnt=true -- PASS
6. tool_access.expected_mcp_benefit = "high" -- PASS
