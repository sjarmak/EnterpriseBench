# Research: Multi-Repo Remaining Types

## Existing Task Format Analysis

### Structure per task directory

- `task.toml` — task definition with repos, checkpoints, metadata, ground_truth
- `ground_truth.json` — structured ground truth with required_files, sufficient_files, and type-specific fields
- `instruction.md` — agent-facing prompt (mirrors task.toml prompt field)
- `checks/` — 2-4 bash scripts, each outputting JSON with score/passed/detail

### task.toml key fields

- Top-level: difficulty_stratum, mcp_suite, repo_set_id, org_scale, verification_modes
- [task]: id, suite, task_type, difficulty, estimated_duration_minutes, session_type, description, prompt
- [[repos]]: url, rev, path, role (primary/consumer/upstream)
- [metadata]: languages, total_loc, dependency_depth, frameworks, multi_repo_pattern
- [[checkpoints]]: name, weight, verifier, description, timeout_seconds
- [artifacts]: required, optional
- [tool_access]: expected_mcp_benefit, mcp_benefit_rationale
- [ground_truth]: tiers, required_files, sufficient_files

### Check script pattern

- Reads $WORKSPACE/agent_output/answer.json or similar output file
- Reads $TASK_DIR/ground_truth.json
- Outputs JSON: {"score": float, "passed": bool, "detail": string}
- Uses python3 for JSON parsing and scoring

### Multi-repo patterns used

- "investigate" — trace across repos to understand behavior
- "propagate" — trace impact of change across repos
- "enforce" — verify contract compliance across repos
- "orchestrate" — coordinate changes across repos

### Difficulty strata

- "dual_repo" — 2 repos
- "tri_repo" — 3 repos
- "multi_repo" — 3+ repos

### Ground truth JSON structure

- task_id, task_type, repos array
- required_files with path, repo, confidence, source
- sufficient_files with path, repo, confidence
- Type-specific fields: error_chain, trigger_conditions, drift_points, etc.

## Key Observations

1. Check scripts are self-contained bash + python3
2. Weights across checkpoints sum to 1.0
3. Real GitHub tags/SHAs are used for repo revisions
4. instruction.md duplicates the prompt from task.toml
5. ground_truth.json has both required_files and type-specific validation data
