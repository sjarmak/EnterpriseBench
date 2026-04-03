# Research: Multi-Repo Deps + Refactor Tasks

## Existing Format Analysis

### task.toml structure (tri-repo)

- Header comment with task title
- `difficulty_stratum = "tri_repo"` (required for all 6 tasks)
- `mcp_suite`, `repo_set_id`, `org_scale`, `verification_modes`
- `[task]` section: id, suite, task_type, difficulty, estimated_duration_minutes, session_type, description, prompt
- `[[repos]]` sections (3 repos for tri-repo): url, rev, path, role
- `[metadata]`: languages, total_loc, dependency_depth, frameworks, multi_repo_pattern
- `[[checkpoints]]`: name, weight, verifier, description, timeout_seconds (weights sum to 1.0)
- `[artifacts]`, `[tool_access]`, `[ground_truth]` sections
- `[[ground_truth.required_files]]` and `[[ground_truth.sufficient_files]]`

### ground_truth.json structure

- task/candidate id, description, repos list
- Type-specific fields: dependency_chain, merge_order, dependency_graph, etc.
- verification object with method and verified flag

### instruction.md

- Standalone markdown restatement of the task
- Context section, Task section, Repos in Workspace, Expected Output

### checks/ scripts

- Bash scripts with `set -euo pipefail`
- Output JSON: `{"score": N, "passed": bool, "reason": "..."}`
- Use grep/python for validation
- Reference `$WORKSPACE` and `$TASK_DIR` environment variables

## Key Patterns

- dependency_graph tasks: output to BLAST_RADIUS.md, check for dep chain tracing
- refactor_orchestration tasks: output to REFACTOR_PLAN.md, check topo order
- Roles: primary/upstream/consumer/intermediary
- multi_repo_pattern: investigate, propagate, orchestrate, enforce
