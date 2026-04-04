# Plan: verify-files-clone

## Step 1: Add `verify_files_exist` function to check_repo_staleness.py

- Groups RequiredFileEntry list by (repo_url, pinned_rev) to deduplicate clones
- For each unique (url, rev): creates a temp dir, does shallow fetch, uses `git ls-tree -r --name-only` to get file listing
- Checks each required file_path against the listing
- Returns a new dataclass `VerifyResult` with: entry, exists (bool), error (optional str)

## Step 2: Add git helper functions

- `_shallow_fetch_file_list(repo_url, rev, work_dir)` -> set[str] or raises
- Uses: git init, git remote add origin <url>, git fetch --depth 1 origin <rev>, git ls-tree -r --name-only FETCH_HEAD
- All via subprocess.run with timeout
- Returns set of file paths in the repo at that rev

## Step 3: Update main() to use clone-and-verify in --verify-files mode

- After scanning required files, call verify_files_exist
- Report missing files (human-readable or JSON)
- Return non-zero exit if any missing

## Step 4: Add format function for verification results

- Human-readable: show missing files grouped by task, pass silently for found files
- JSON: include full results with exists/missing status

## Step 5: Write tests

- Mock subprocess.run to simulate git commands
- Test: all files exist -> exit 0
- Test: some files missing -> exit 1 with report
- Test: git clone failure -> graceful error handling
- Test: JSON output mode with verification results
- Test: grouping by (url, rev) deduplication
- Ensure all existing tests still pass
