# Plan: crnt-per-checkpoint-upgrade

## Step 1: Update CheckpointInfo dataclass

- Add `repo_deps: tuple[str, ...] = ()` field to the frozen dataclass

## Step 2: Update extract_checkpoints

- Read `repo_deps` from each checkpoint dict, convert to tuple of strings, default to empty tuple

## Step 3: Update map_checkpoints_to_repos

- For each checkpoint, if `cp.repo_deps` is non-empty, use `set(cp.repo_deps)` as that checkpoint's repo set
- If `cp.repo_deps` is empty, fall back to existing heuristic (gt_repos or all_repo_paths)

## Step 4: Add test fixtures

- `_make_repo_deps_config`: 2-repo config, checkpoint A has repo_deps=["repo1"], checkpoint B has repo_deps=["repo2"]
- `_make_mixed_config`: 2-repo config, one checkpoint has repo_deps, the other doesn't

## Step 5: Add test cases

- TestExtractCheckpoints: test repo_deps extraction
- TestMapCheckpointsToRepos: test repo_deps anchoring, test mixed config
- TestComputeMaxScore: test removing repo1 in repo_deps config gives weight(B) not 0.0
- TestEvaluateCRNT: test dual-repo with repo_deps passes CRNT with differentiated scores

## Step 6: Run tests and verify all pass
