# Research: verify-files-clone

## Current State

- `check_repo_staleness.py` has `--verify-files` flag that scans task.toml files and lists required_files
- `scan_required_files()` returns `RequiredFileEntry` dataclasses with repo_url, pinned_rev, file_path
- Currently returns exit 0 always -- no actual verification against repos
- `RequiredFileEntry` is frozen dataclass with: task_id, task_path, file_path, repo_name, repo_url, pinned_rev, confidence

## Key Design Points

- Need to group entries by (repo_url, pinned_rev) to avoid cloning same repo+rev multiple times
- Use shallow clone + sparse checkout to minimize disk/network
- Git commands: `git clone --depth 1 --no-checkout --filter=blob:none <url> <dir>`, then `git checkout <rev> -- <files>` or use `git ls-tree` to check existence without checkout
- Better approach: `git clone --depth 1 --no-checkout`, then `git ls-tree -r --name-only <rev>` to list all files, check membership
- Even better for tags/SHAs: `git init` + `git remote add` + `git fetch --depth 1 origin <rev>` + `git ls-tree -r FETCH_HEAD`
- For non-zero exit: return 1 if any files missing

## Existing Tests

- 345 lines in test_staleness_verify_files.py covering scan, format, CLI, existing staleness
- Tests use tmp_path fixtures and subprocess calls
- Need to preserve all existing tests, add new ones for clone-and-verify logic

## Conventions

- Uses frozen dataclasses
- Type annotations on all functions
- tomllib/tomli for TOML parsing
- subprocess not currently used in main module (only in tests)
