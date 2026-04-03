# Plan: repo-versions-manifest

## Step 1: Create manifest generator script

- Scan all `benchmarks/**/task.toml` (skip `_archived/`)
- Parse each file with tomllib
- Extract `[[repos]]` entries (url, rev)
- Deduplicate by (url, rev) pair
- Output `configs/repo_versions.json` with entries: `{url, pinned_rev, last_verified}`
- Set `last_verified` to today's date for initial generation

## Step 2: Run generator to create initial `configs/repo_versions.json`

## Step 3: Create `scripts/infra/check_repo_staleness.py`

- Read `configs/repo_versions.json`
- For each entry, check if `last_verified` > 6 months ago
- Print warnings for stale repos
- `--json` flag for machine-readable output
- Callable via `python scripts/infra/check_repo_staleness.py`

## Step 4: Write tests for staleness check logic

- Test stale detection (date > 6 months)
- Test fresh detection (date < 6 months)
- Test JSON output mode
- Test edge cases (exactly 6 months)

## Step 5: Commit
