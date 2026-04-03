# Research: sg-indexing-fix

## Current Structure

`configs/sg_indexing_list.json` has:

- Top-level metadata: `_description`, `_generated`, `_total_unique_repos` (131), `_total_mirror_files` (117)
- `suites` object with 5 suites, each having `_status`, `_indexed_count` (all 0), `_repo_count`, `_task_count`
- `repos` array of 131 repo entries, each with: `sg_name`, `github_repo`, `commit`, `_language`, `_loc_estimate`, `_tier`, `_indexed` (all false), `_task_count`, optional `_suites`

## Key Observations

1. Per-repo `_indexed` boolean already exists in the flat `repos` array
2. Suite-level `_indexed_count` is hardcoded to 0 — not computed from per-repo `_indexed` values
3. 72 repos have no `_suites` field (orphaned from suite tracking)
4. The `suites` section lacks per-repo breakdown — you can't see which repos belong to which suite from the suites section alone

## Generator Script

`scripts/generate_sg_index.py`:

- Reads `configs/sg_mirrors/*.json` and `benchmarks/` directory structure
- Builds flat repo list with `_indexed: False` hardcoded
- Computes suite stats but doesn't track per-repo indexing status
- Suite `_indexed_count` always set to 0

## Gap

The suite-level `_indexed_count` should be dynamically computed from the per-repo `_indexed` values. A verification script should validate this and provide summary reporting.
