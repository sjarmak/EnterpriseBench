# Test Results: convert-incident-inv-004

## CRNT Validator

- Command: `python3 scripts/validation/crnt_validator.py benchmarks/incident_response/incident-investigation-004/task.toml --json`
- passes_crnt: true
- Remove moby: max_score_without = 0.0, lost all 4 checkpoints (passes threshold)
- Remove containerd: max_score_without = 0.55, lost error_chain_trace + affected_services (passes threshold)
- Scores are differentiated: 0.0 vs 0.55

## Shell Script Syntax

- check_root_cause.sh: OK (bash -n passes)
- check_error_chain.sh: OK (bash -n passes)
- check_affected_services.sh: OK (bash -n passes)
- check_remediation.sh: OK (bash -n passes)

## Acceptance Criteria Verification

1. difficulty_stratum = "dual_repo" -- PASS
2. 2 [[repos]] entries (moby + containerd) -- PASS
3. containerd pinned to v1.7.24 -- PASS
4. repo_deps differentiated across checkpoints -- PASS
5. ground_truth.required_files includes containerd entries -- PASS
6. tool_access has expected_mcp_benefit = "high" -- PASS
7. CRNT passes with differentiated scores -- PASS
8. All check scripts valid bash -- PASS
