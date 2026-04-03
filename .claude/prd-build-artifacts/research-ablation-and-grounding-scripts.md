# Research: ablation-and-grounding-scripts

## crnt_validator.py findings

- `parse_toml()` reads task.toml via tomllib/tomli
- `extract_repos()` returns `tuple[RepoInfo, ...]` from config
- `extract_checkpoints()` returns `tuple[CheckpointInfo, ...]` with `repo_deps` field
- `map_checkpoints_to_repos()` maps checkpoint names to set of repo paths they depend on
- `generate_ablations()` creates one `AblatedConfig` per repo (task_id, removed_repo, remaining_repos, original_config)
- `compute_max_score_without_repo()` returns (max_score, lost_checkpoint_names)
- `AblatedConfig.to_dict()` produces modified config with repo removed from repos list

## run_task.py findings

- Image tag convention: `eb-{task_id}{mode_suffix}` (e.g., `eb-task-mcp_only`)
- Output dir convention: `results/runs/<task_id>/<mode>/`
- Docker build: `_docker_build(dockerfile_path, image_tag)` using `docker build -f`
- Docker create/start/exec pattern for container lifecycle
- `_generate_dockerfile()` uses `scripts/sandbox/dockerfile_generator.py`
- Verifier scripts copied to `/workspace/.verifiers/` inside container
- `_parse_task()` validates task.toml structure

## task.toml structure (multi-repo)

- `[[repos]]` entries with url, rev, path, role
- `[[checkpoints]]` with name, weight, verifier, description, optional repo_deps
- `repo_deps` is per-checkpoint list of repo paths the checkpoint depends on
- Currently no tasks have repo_deps populated (field exists in schema/code but not yet in task files)
- Fallback: `map_checkpoints_to_repos()` uses ground_truth.required_files or all repos

## Docker tagging

- Standard: `eb-{task_id}` or `eb-{task_id}-{mode}`
- Ablation convention should be: `eb-{task_id}-ablate-{excluded_repo}`

## Test patterns

- Tests import from `scripts.validation.crnt_validator` (module path)
- Use helper functions like `_make_multi_repo_config()` for fixtures
- Standard pytest with no special fixtures beyond conftest.py
