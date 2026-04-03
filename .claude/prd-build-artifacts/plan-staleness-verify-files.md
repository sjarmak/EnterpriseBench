# Plan: staleness-verify-files

## Steps

1. Add tomllib import to check_repo_staleness.py (try/except pattern)
2. Add frozen dataclass `RequiredFileEntry` with fields: task_id, file_path, repo_name, repo_url, pinned_rev, confidence
3. Add `scan_required_files(benchmarks_dir)` function:
   - Glob for `**/task.toml` excluding `_archived/`
   - Parse each TOML, extract repos and ground_truth.required_files
   - Cross-reference repo name to get url and rev
   - Return list of RequiredFileEntry
4. Add `format_verify_files_report(entries, json_output)` function
5. Add `--verify-files` flag to argparse
6. In main(), if --verify-files: call scan + format, exit
7. Create tests/test_staleness_verify_files.py with:
   - Test --verify-files in help text
   - Test scan_required_files with mock task.toml (tmp_path)
   - Test cross-referencing repos correctly
   - Test JSON output format
   - Test human-readable output format
   - Test that existing staleness check still works
