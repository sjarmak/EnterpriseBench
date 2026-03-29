# CSB → EnterpriseBench Migration Pilot Report

## Summary

- **Tasks attempted**: 10
- **Migration succeeded**: 10
- **Migration failed**: 0
- **Validation passed**: 10
- **Validation failed**: 0

## Per-Task Results

| Task ID | Migration | Validation | Warnings | Errors |
|---------|-----------|------------|----------|--------|
| ccx-compliance-052 | Pass | Pass | 0 | - |
| ccx-incident-032 | Pass | Pass | 0 | - |
| ccx-dep-trace-106 | Pass | Pass | 0 | - |
| ansible-galaxy-tar-regression-prove-001 | Pass | Pass | 1 | - |
| bustub-hyperloglog-impl-001 | Pass | Pass | 1 | - |
| ansible-abc-imports-fix-001 | Pass | Pass | 0 | - |
| beam-pipeline-builder-refac-001 | Pass | Pass | 0 | - |
| ceph-rgw-auth-secure-001 | Pass | Pass | 0 | - |
| aspnetcore-code-review-001 | Pass | Pass | 0 | - |
| camel-routing-arch-001 | Pass | Pass | 0 | - |

## Common Warnings

- **repos**: 2 occurrence(s)

## Fields That Could Not Be Auto-Mapped

- `metadata.max_complexity` — not available in CSB metadata
- `metadata.frameworks` — available in reviewers.json but not reliably structured
- `metadata.multi_repo_pattern` — requires manual classification
- `ground_truth.sufficient_files` — CSB only has required files in ground_truth.json
- `tool_access.mcp_benefit_rationale` — requires human judgment
- Multiple checkpoints — CSB has single test.sh; splitting requires manual analysis

## Recommendations for Full Migration

1. **ID normalization**: Several CSB IDs use mixed case (e.g., 'CCX-compliance-052').
   The normalizer handles this, but manual review recommended for edge cases.
2. **Multi-checkpoint splitting**: All migrated tasks have a single checkpoint (weight=1.0).
   For the full migration, analyze test.sh to identify natural checkpoints.
3. **Ground truth enrichment**: CSB ground_truth.json files are curator-generated.
   Add deterministic tier via static analysis before benchmark runs.
4. **Repo URL resolution**: sg-evals mirror URLs need mapping to real GitHub repos.
   Build a mirror→canonical URL lookup table.
5. **SDLC tasks without repo field**: Some SDLC tasks don't specify a repo in task.toml.
   These need manual repo assignment from the task's Docker environment.
6. **Stratum classification**: Auto-classification uses repo count + org_scale.
   Manual review needed for calibration vs large_single boundary.

