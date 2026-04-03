# Research: Multi-Repo Task Authoring

## Schema Requirements (schemas/task.schema.json)

- Required top-level: task, repos, checkpoints, artifacts
- task required: id, suite, difficulty, session_type
- task.id pattern: `^[a-z][a-z0-9-]+-\d{3}$`
- repos: 1-5 items, each with url/rev/path required, role optional (primary/dependency/consumer/upstream/intermediary/deprecated_upstream)
- checkpoints: 1-5, each with name/weight/verifier required
- difficulty_stratum enum: calibration, large_single, dual_repo, multi_repo, monorepo_cross_package, tri_repo
- multi_repo_pattern enum: propagate, investigate, enforce, orchestrate
- verification_modes: deterministic, llm_curator, solve_verified, structural_match

## Existing Multi-Repo Reference (dep-traversal-001)

- 3 repos (lodash, webpack, jest), stratum "multi_repo"
- Top-level fields: difficulty_stratum, mcp_suite, repo_set_id, org_scale, verification_modes
- Repos have role field (primary, consumer)
- metadata includes multi_repo_pattern, dependency_depth
- 4 checkpoints with weights summing to 1.0
- ground_truth with required_files and sufficient_files

## Existing Single-Repo Patterns per Type

1. **config_drift** (config-drift-001): enforce pattern, yaml/go-template, Helm chart focus
2. **db_schema_evolution** (schema-evolution-001): Django model changes, Python/JS
3. **dead_code_necropsy** (dead-code-001): React legacy event system, JS
4. **error_provenance** (err-provenance-01): Kubernetes Job validation, Go
5. **support_code_mapping** (support-mapping-001): Envoy connection pool, C++

## Key Patterns for Dual-Repo Tasks

- difficulty_stratum = "dual_repo"
- 2 repos with roles (primary + consumer/dependency/upstream)
- dependency_depth = 2
- multi_repo_pattern from enum
- ground_truth.required_files spanning both repos
- Prompts reference cross-repo investigation

## Authoring Guide Key Points

- Task dirs: benchmarks/{suite}/{task-id}/
- Verifier scripts output JSON: {"score": float, "passed": bool, "reason": str}
- Use set -euo pipefail in all scripts
- Checkpoint weights sum to ~1.0
- Pin repos to specific tags/commits
