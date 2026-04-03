# CRNT Framework Research

## Task Schema (schemas/task.schema.json)

- `repos`: array of 1-5 objects, each with `url`, `rev`, `path` (required), `role` (optional: primary/dependency/consumer/upstream/intermediary/deprecated_upstream)
- `checkpoints`: array of 1-5 objects with `name`, `weight`, `verifier`, `description`, `timeout_seconds`
- `difficulty_stratum`: includes "dual_repo", "multi_repo", "tri_repo", "monorepo_cross_package" — these are the multi-repo strata
- `ground_truth.required_files`: each has `path` and `repo` — maps files to specific repos

## Example: dep-traversal-001

- 3 repos: lodash (primary), webpack (consumer), jest (consumer)
- 4 checkpoints: identify_cve (0.10), find_direct_deps (0.30), trace_transitive_paths (0.35), version_analysis (0.25)
- ground_truth.required_files maps files to repos — this is how we anchor checkpoints to repos

## TOML Parsing

- `scripts/infra/create_sg_mirrors.py` has `parse_toml()` that uses tomllib (3.11+) with tomli fallback, plus a manual fallback parser
- `run_task.py` imports `parse_toml` from `create_sg_mirrors`

## CRNT Design Implications

- For ablation: remove one repo from the `repos` list and check if ground_truth files tied to that repo would be missing
- A checkpoint is "anchored" to a repo if ground_truth.required_files references that repo
- CRNT pass = removing ANY single repo causes ≤60% max achievable score (because checkpoints depending on that repo's files can't be completed)
