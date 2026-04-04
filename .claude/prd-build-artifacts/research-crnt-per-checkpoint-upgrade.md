# Research: crnt-per-checkpoint-upgrade

## CheckpointInfo dataclass

- Frozen dataclass with fields: name (str), weight (float), verifier (str), description (str, default="")
- No repo_deps field currently

## extract_checkpoints

- Reads from config["checkpoints"] list of dicts
- Creates CheckpointInfo for each, extracting name, weight, verifier, description

## map_checkpoints_to_repos

- Current heuristic: builds gt_repos from ground_truth.required_files[*].repo
- If no gt_repos, anchors ALL checkpoints to ALL repos (conservative)
- If gt_repos exist, anchors EVERY checkpoint to ALL gt_repos (no per-checkpoint differentiation)
- This means removing any repo with required_files loses ALL checkpoints

## compute_max_score_without_repo

- Gets checkpoint->repos mapping, marks checkpoint as "lost" if removed_repo is in its deps
- Returns (remaining_score, lost_checkpoint_names)

## Test structure

- Fixtures: \_make_multi_repo_config (3-repo), \_make_single_repo_config, \_make_partial_dependency_config (2-repo), \_make_no_ground_truth_config
- Test classes: TestExtractRepos, TestExtractCheckpoints, TestMapCheckpointsToRepos, TestGenerateAblations, TestComputeMaxScore, TestEvaluateCRNT, TestFormatResult, TestWriteAblatedConfigs, TestParseTOML, TestCLI

## Key insight

- The upgrade needs per-checkpoint repo_deps that override the ground_truth heuristic per-checkpoint
- When repo_deps is present on a checkpoint, that checkpoint is anchored ONLY to those repos
- When absent, fall back to existing heuristic (all gt_repos)
