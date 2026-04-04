# Test Results: crnt-per-checkpoint-upgrade

## Run: pytest tests/test_crnt_validator.py -v

41 passed in 0.04s

### New tests added (10):

- TestExtractCheckpoints::test_extracts_repo_deps - PASSED
- TestExtractCheckpoints::test_repo_deps_default_empty - PASSED
- TestMapCheckpointsToRepos::test_repo_deps_anchors_to_declared_repos - PASSED
- TestMapCheckpointsToRepos::test_mixed_config_anchoring - PASSED
- TestComputeMaxScore::test_repo_deps_removing_repo1_keeps_cp_b - PASSED
- TestComputeMaxScore::test_repo_deps_removing_repo2_keeps_cp_a - PASSED
- TestComputeMaxScore::test_mixed_config_removing_repo1 - PASSED
- TestComputeMaxScore::test_mixed_config_removing_repo2 - PASSED
- TestEvaluateCRNT::test_repo_deps_dual_repo_passes_crnt - PASSED
- TestEvaluateCRNT::test_repo_deps_differentiated_scores - PASSED

### Existing tests (31): All PASSED (no regressions)

## Acceptance criteria verification:

1. repo_deps config: removing repo1 yields max_score=0.5 (weight of cp_b), NOT 0.0 - VERIFIED
2. Configs without repo_deps use ground_truth heuristic unchanged - VERIFIED (all existing tests pass)
3. Mixed configs: repo_deps checkpoints use explicit deps, others fall back - VERIFIED
4. All tests green - VERIFIED (41/41)
5. CheckpointInfo has optional repo_deps field - VERIFIED
6. extract_checkpoints reads repo_deps - VERIFIED
